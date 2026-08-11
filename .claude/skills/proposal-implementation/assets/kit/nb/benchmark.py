"""Screening benchmark: train both implementations in one reduced environment.

This runs in the target repository, with the target's interpreter and its torch —
never the forge's. It is deliberately small: a ResNet-18 backbone and a stratified
slice, sized so several seeds finish in the time one full run would take.

Read every number together with the reduction printed beside it. A reduced setting
can invert a result: a method that needs capacity or volume to show its advantage
loses here and wins at full scale. This screens; it does not decide.

What speed buys is repetition. One run cannot separate a difference from its own
noise, so the default is several seeds and the report carries dispersion, never a
bare mean.

    python benchmark.py --config config.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
import sys
from pathlib import Path
from typing import Callable

from verdict import DESCRIPTIVE, HIGHER, LOWER, judge, render, tally

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset

DATASETS = {"CIFAR10": 10, "CIFAR100": 100, "MNIST": 10}


# The dimensions the trained setting measures, and which direction wins each. The
# synthetic sweep reports its own dimensions through the same shape and the same
# rules, so both settings produce one comparable table.
DIMENSIONS = {
    "accuracy": HIGHER,
    "seconds": LOWER,
    "peakMiB": LOWER,
    "parameters": DESCRIPTIVE,
}


@dataclass
class Reduction:
    """Everything that makes this a screening run rather than the benchmark."""

    setting: str = "trained"
    dataset: str = "CIFAR10"
    backbone: str = "resnet18"
    fraction: float = 0.1
    epochs: int = 1
    batch_size: int = 64
    seeds: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    revision: str = ""
    device: str = "cpu"


def stratified_indices(targets: list[int], fraction: float, classes: int,
                       generator: torch.Generator) -> list[int]:
    """A slice that keeps every class, drawn per class rather than at random.

    The proposal requires every class to be present in the source collection the
    local correspondence uses. A random slice can drop one, which leaves that
    correspondence undefined — and the failure would look like a defect of the
    method while being a defect of the sampling. So the slice is drawn class by
    class, and a class that cannot contribute at least one example is an error
    rather than a silently smaller slice.
    """
    by_class: dict[int, list[int]] = {c: [] for c in range(classes)}
    for index, label in enumerate(targets):
        by_class[int(label)].append(index)

    chosen: list[int] = []
    for label, pool in by_class.items():
        if not pool:
            raise ValueError(f"class {label} is absent from the dataset split")
        take = max(1, int(len(pool) * fraction))
        order = torch.randperm(len(pool), generator=generator).tolist()
        chosen.extend(pool[i] for i in order[:take])
    return chosen


def load_split(reduction: Reduction, root: Path, train: bool, seed: int):
    """The common environment. Both implementations see exactly this."""
    from torchvision import datasets, transforms  # imported late: optional dependency

    classes = DATASETS[reduction.dataset]
    grayscale = reduction.dataset == "MNIST"
    steps = [transforms.Resize(32), transforms.ToTensor()]
    if grayscale:
        steps.insert(1, transforms.Grayscale(num_output_channels=3))
    factory = getattr(datasets, reduction.dataset)
    full = factory(root=str(root), train=train, download=True,
                   transform=transforms.Compose(steps))

    targets = full.targets.tolist() if torch.is_tensor(full.targets) else list(full.targets)
    generator = torch.Generator().manual_seed(seed)
    indices = stratified_indices(targets, reduction.fraction, classes, generator)
    return Subset(full, indices), classes


def backbone(name: str, classes: int) -> nn.Module:
    from torchvision import models

    if name != "resnet18":
        raise ValueError(f"unsupported backbone {name!r}: the probe is deliberately small")
    model = models.resnet18(weights=None, num_classes=classes)
    return model


@dataclass
class RunMetrics:
    accuracy: float
    seconds: float
    peak_mib: float
    parameters: int


def train_and_score(build: Callable[[int], nn.Module], reduction: Reduction,
                    root: Path, seed: int) -> RunMetrics:
    """One seed, end to end, with cost measured around the whole thing."""
    torch.manual_seed(seed)
    train_set, classes = load_split(reduction, root, train=True, seed=seed)
    test_set, _ = load_split(reduction, root, train=False, seed=seed)
    device = torch.device(reduction.device)

    model = build(classes).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()
    loader = DataLoader(train_set, batch_size=reduction.batch_size, shuffle=True)

    tracemalloc.start()
    started = time.perf_counter()
    model.train()
    for _ in range(reduction.epochs):
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss_fn(model(images), labels).backward()
            optimizer.step()
    seconds = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] / (1024 * 1024)
    tracemalloc.stop()

    model.eval()
    correct = total = 0
    with torch.no_grad():
        for images, labels in DataLoader(test_set, batch_size=reduction.batch_size):
            images, labels = images.to(device), labels.to(device)
            correct += int((model(images).argmax(dim=1) == labels).sum())
            total += int(labels.numel())

    return RunMetrics(
        accuracy=correct / total if total else float("nan"),
        seconds=seconds,
        peak_mib=peak,
        parameters=sum(p.numel() for p in model.parameters()),
    )


def summarize(runs: list[RunMetrics]) -> dict:
    """Mean and dispersion. A bare mean over several seeds hides the only thing
    several seeds were run to reveal."""
    def spread(values: list[float]) -> dict:
        return {"mean": statistics.fmean(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "n": len(values)}

    return {
        "accuracy": spread([r.accuracy for r in runs]),
        "seconds": spread([r.seconds for r in runs]),
        "peakMiB": spread([r.peak_mib for r in runs]),
        "parameters": runs[0].parameters if runs else None,
    }


def compare(builders: dict[str, Callable[[int], nn.Module] | None],
            reduction: Reduction, root: Path) -> dict:
    """Run every implementation that can be driven into this exact setting.

    A builder of None means the implementation could not be brought into the common
    reduction as it stands. That is reported as `not applicable` with its reason and
    never filled with a number: inventing one would describe a setting nobody ran.
    """
    results: dict[str, dict] = {}
    for label, build in builders.items():
        if build is None:
            results[label] = {"applicable": False,
                              "reason": "cannot be driven into the common reduction "
                                        "as it stands, and a baseline is never edited "
                                        "to make a comparison possible"}
            continue
        runs = [train_and_score(build, reduction, root, seed) for seed in reduction.seeds]
        results[label] = {"applicable": True, **summarize(runs)}
    return results


def require_target_interpreter() -> Path:
    """Refuse to run under any interpreter that is not this repository's own.

    The contract has said this in prose in three places, and nothing checked it. For a
    benchmark it is not a hygiene rule: wall time and peak memory *are* the
    measurement, so an interpreter from somewhere else does not give a slightly
    inaccurate result — it gives a correct measurement of the wrong environment, and
    the summary would attribute it to this repository.

    The file sits at <repo>/<Name>/Notebooks/benchmark.py, so the repository is two
    levels up, and the interpreter has to live inside it.
    """
    repository = Path(__file__).resolve().parents[2]
    prefix = Path(sys.prefix).resolve()
    try:
        prefix.relative_to(repository)
    except ValueError:
        raise SystemExit(
            f"refusing to run under {prefix}\n"
            f"  this benchmark must use {repository}'s own virtualenv, because wall "
            f"time and peak memory are the measurement: another interpreter would "
            f"measure a different environment correctly and report it as this one.\n"
            f"  run the notebook with {repository}/.venv/bin/python, or invoke this "
            f"file with it directly."
        )
    return repository


def main(argv: list[str] | None = None) -> int:
    require_target_interpreter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="JSON holding the reduction")
    parser.add_argument("--data", default="./.benchmark-data", help="dataset cache")
    parser.add_argument("--out", required=True, help="where to write the summary")
    args = parser.parse_args(argv)

    reduction = Reduction(**json.loads(Path(args.config).read_text(encoding="utf-8")))
    if reduction.dataset not in DATASETS:
        raise SystemExit(f"unknown dataset {reduction.dataset!r}: pick one of {sorted(DATASETS)}")

    # Filled in from the wiring `probe` proposed and the user completed. A bare
    # backbone is not either implementation: training one and reporting it would
    # measure the backbone and call it the method.
    #
    # Both stay unset here on purpose. `build_wiring` is written into the target
    # repository as part of the flow, and its absence is refused below rather than
    # silently producing a table about nothing.
    try:
        from wiring import build_baseline, build_new  # written for this repository
    except ImportError as missing:
        raise SystemExit(
            "wiring.py is missing: this benchmark has nothing to compare.\n"
            f"  ({missing})\n"
            "Run `probe` and complete the wiring it proposes — which modules carry "
            "the trainable terms, where the backbone enters, what the head predicts "
            "over — then write it as wiring.py beside this file. Running without it "
            "would train a bare backbone and report it as the method."
        )

    builders: dict[str, Callable[[int], nn.Module] | None] = {
        "new": lambda classes: build_new(classes, reduction.backbone),
        "baseline": (lambda classes: build_baseline(classes, reduction.backbone))
                    if build_baseline is not None else None,
    }

    measured = compare(builders, reduction, Path(args.data))
    # One row per dimension, both sides side by side, so the verdict rules that serve
    # the synthetic sweep serve this one unchanged.
    rows = []
    for dimension, better in DIMENSIONS.items():
        def side(label):
            entry = measured.get(label, {})
            if not entry.get("applicable"):
                return None
            value = entry.get(dimension)
            return value if isinstance(value, dict) else {"mean": value, "stdev": 0.0, "n": 1}
        rows.append({"dimension": dimension, "better": better,
                     "baseline": side("baseline"), "new": side("new")})

    judged = judge(rows)
    summary = {
        "kind": "screening",
        "setting": reduction.setting,
        "revision": reduction.revision,
        "reduction": asdict(reduction),
        "comparison": judged,
        "tally": tally(judged),
    }
    print(render(judged, {**asdict(reduction), "seeds": len(reduction.seeds)}))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
