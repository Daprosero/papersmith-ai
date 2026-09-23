"""yamllite parser tests: the spec's own YAML, the repo's config, and refusals."""

from __future__ import annotations

import unittest
from pathlib import Path

from papersmith.yamllite import YamlliteError, loads

SPEC_YAML = '''\
version: "1"
name: "sparse-autoencoder-audit"
title: "Mechanistic Interpretability of Sparse Autoencoders"
venue_target: "NeurIPS-2026"

skills:
  - paper-ingestion
  - proposal-deliberation
  - proposal-implementation
  - remote-execution
  - kaggle-accounts
  - skill-audit

environment:
  python: ">=3.11"
  node: ">=20.0.0"
  cuda: "12.2"

compute_targets:
  default: "kaggle-gpu-pool"
  targets:
    local-workstation:
      provider: "local"
      device: "cuda:0"
      max_parallel_jobs: 2
      scratch_dir: ".scratch/runs"
    kaggle-gpu-pool:
      provider: "kaggle"
      account_pool: "default"
      accelerator: "GPU_T4_X2"        # GPU_T4_X2 | GPU_P100 | TPU_V3_8 | NONE
      internet_access: true
      max_timeout_hours: 9
      auto_pull_artifacts: true
    slurm-cluster:
      provider: "remote-ssh"
      host: "hpc.university.edu"
      partition: "gpu-a100"
      nodes: 1
      gpus_per_node: 2
      walltime: "12:00:00"

execution_profiles:
  smoke_and_invariants:
    target: "local-workstation"
    entrypoint: "pytest implementations/{paper_slug}/tests/test_invariants.py"
    env_vars:
      PYTHONPATH: "implementations/{paper_slug}/src"
      CUDA_VISIBLE_DEVICES: "0"
    timeout_seconds: 300
  sweep_training:
    target: "kaggle-gpu-pool"
    bootstrap: "skills/remote-execution/assets/runner_bootstrap.py"
    entrypoint: "python implementations/{paper_slug}/src/train.py"
    sharding:
      enabled: true
      strategy: "grid"
      parameter: "--seed"
      values: [42, 1337, 2026, 9999]
      distribute_across_accounts: true
    resources:
      min_ram_gb: 16
      gpu_vram_gb: 16
    artifacts:
      collect:
        - "checkpoints/*.pt"
        - "metrics/*.json"
        - "figures/*.png"
      destination: "kaggle-inbox/{job_id}/"
'''


class YamlliteTests(unittest.TestCase):
    def test_spec_example_parses(self) -> None:
        data = loads(SPEC_YAML)
        assert data["version"] == "1"
        assert data["name"] == "sparse-autoencoder-audit"
        assert data["skills"] == [
            "paper-ingestion",
            "proposal-deliberation",
            "proposal-implementation",
            "remote-execution",
            "kaggle-accounts",
            "skill-audit",
        ]
        targets = data["compute_targets"]["targets"]
        assert data["compute_targets"]["default"] == "kaggle-gpu-pool"
        assert targets["local-workstation"]["max_parallel_jobs"] == 2
        assert targets["local-workstation"]["max_parallel_jobs"] == 2
        assert targets["kaggle-gpu-pool"]["internet_access"] is True
        assert targets["kaggle-gpu-pool"]["max_timeout_hours"] == 9
        assert targets["slurm-cluster"]["nodes"] == 1
        assert targets["slurm-cluster"]["walltime"] == "12:00:00"
        sharding = data["execution_profiles"]["sweep_training"]["sharding"]
        assert sharding["values"] == [42, 1337, 2026, 9999]
        assert sharding["distribute_across_accounts"] is True
        artifacts = data["execution_profiles"]["sweep_training"]["artifacts"]
        assert artifacts["collect"] == ["checkpoints/*.pt", "metrics/*.json", "figures/*.png"]
        assert data["execution_profiles"]["smoke_and_invariants"]["timeout_seconds"] == 300

    def test_repo_papersmith_yaml_parses(self) -> None:
        path = Path(__file__).resolve().parent.parent / "papersmith.yaml"
        data = loads(path.read_text(encoding="utf-8"))
        ingestion = data["paper_ingestion"]
        assert ingestion["engine"] == "marker"
        assert ingestion["mode"] == "fast"
        assert ingestion["strip_references"] is True
        assert ingestion["source_base"] == "guidance"
        assert ingestion["source_roots"] == []

    def test_quoted_scalars_keep_specials(self) -> None:
        data = loads('title: "a # b: c"\nother: \'single "quote"\'\nwalltime: "12:00:00"')
        assert data["title"] == "a # b: c"
        assert data["other"] == 'single "quote"'
        assert data["walltime"] == "12:00:00"

    def test_unquoted_colon_in_value_is_kept(self) -> None:
        assert loads("walltime: 12:00:00")["walltime"] == "12:00:00"

    def test_scalar_coercion(self) -> None:
        data = loads("a: 1\nb: 1.5\nc: true\nd: false\ne: null\nf: ~\ng: text\nh: 007")
        assert data["a"] == 1
        assert data["b"] == 1.5
        assert data["c"] is True
        assert data["d"] is False
        assert data["e"] is None
        assert data["f"] is None
        assert data["g"] == "text"
        assert data["h"] == 7

    def test_comments_and_blanks(self) -> None:
        data = loads("# header\n\nkey: value  # trailing\n\nother: x\n")
        assert data == {"key": "value", "other": "x"}

    def test_nested_sequences_of_mappings(self) -> None:
        text = """\
profiles:
  - name: x
    value: 1
  - name: y
    value: 2
items:
  - scalar
  - "quoted scalar"
empty: []
"""
        data = loads(text)
        assert data["profiles"] == [{"name": "x", "value": 1}, {"name": "y", "value": 2}]
        assert data["items"] == ["scalar", "quoted scalar"]
        assert data["empty"] == []

    def test_sequence_item_with_nested_block(self) -> None:
        data = loads("things:\n  -\n    a: 1\n    b: 2\n  -\n    a: 3\n")
        assert data["things"] == [{"a": 1, "b": 2}, {"a": 3}]

    def test_document_marker_and_empty_documents(self) -> None:
        assert loads("---\nkey: value\n") == {"key": "value"}
        assert loads("") is None
        assert loads("# only a comment\n") is None

    def test_duplicate_key_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "duplicate key"):
            loads("a: 1\na: 2\n")

    def test_tab_indentation_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "tabs are not allowed"):
            loads("a:\n\tb: 1\n")

    def test_anchor_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "unsupported YAML construct"):
            loads("a: &anchor value\n")

    def test_flow_mapping_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "flow mappings are not supported"):
            loads("a: {b: 1}\n")

    def test_nested_flow_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "nested flow"):
            loads("a: [1, [2]]\n")

    def test_unterminated_quote_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "unterminated quoted scalar"):
            loads('a: "never closed\n')

    def test_bare_dash_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "sequence item '-' needs nested content"):
            loads("a:\n  -\nnext: 1\n")

    def test_missing_colon_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "expected 'key: value'"):
            loads("just a scalar line\n")

    def test_trailing_junk_after_quoted_refused(self) -> None:
        with self.assertRaisesRegex(YamlliteError, "trailing characters"):
            loads('a: "x" junk\n')

    def test_error_reports_line_number(self) -> None:
        with self.assertRaises(YamlliteError) as context:
            loads("a: 1\nb: 2\nc: 3\nd: 4\ne: 5\nf: [1, {x}]\n")
        assert context.exception.line == 6
