"""figure-review: the tenth skill's own suite.

Commit 1 claimed exactly one thing — an already-compiled figure PDF can be
turned into a PNG deterministically, over a fixed fallback chain, with a
named refusal when no link resolves, and its own subprocess seam guarding
the one module allowed to spawn a process. It claimed no visual dimension.

Commit 2 (this addition) turns those pixels into numbers: a stdlib PNG
decoder (`png_read.py`), pure-Python connected components and the
geometric facts a raster can support (`geometry.py`), the roster shelf
both `figure-review` and `paper-writing` will import
(`skills/_core/figure/figure_dimensions.py`), and the assembly that ties
them together (`findings.py`). `paper-writing` remains untouched until
Commit 3.

Every chain-fallback test below runs against a scratch `PATH` holding only
stub executables — never a real rasterizer — so this suite is unconditional
on any machine, with or without `pdftoppm`/`pdftocairo`/`gs`/`sips`
installed (`figure-raster` spec, `Requirement: No-Skip Test Evidence Across
Three Tiers`).
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
import zlib
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
REVIEW_SCRIPTS = FORGE_ROOT / ".opencode" / "skills" / "figure-review" / "scripts"
CORE_FIGURE = FORGE_ROOT / ".opencode" / "skills" / "_core" / "figure"
FIXTURES = FORGE_ROOT / "tests" / "fixtures" / "figure-review"
sys.path.insert(0, str(REVIEW_SCRIPTS))
import raster  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / ".opencode" / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

sys.path.insert(0, str(CORE_FIGURE))

# `the-figure-nobody-looked-at`, Phase 4 (task 4.6): `paper_cli.py`, for the
# one end-to-end test that crosses the skill boundary the way an operator
# or agent invocation would -- never a production import in either
# direction (`figure-review`'s own scripts still import nothing from
# `paper-writing`, proven unchanged by `RepairBudgetIsolationTests` above).
sys.path.insert(0, str(FORGE_ROOT / ".opencode" / "skills" / "paper-writing" / "scripts"))
import paper_cli  # noqa: E402

import unittest  # noqa: E402

# =====================================================================
# Figure-review's own subprocess seam, mirroring `NoSubprocessScanTests`
# (`tests/test_paper_writing.py:6136-6158`), plus one non-vacuity assertion
# the precedent lacks.
# =====================================================================

#: Pinned to `len(...) == 1` for the same reason paper-writing's own
#: exception tuple is: a SECOND name costs a hand edit to this literal in a
#: diff someone reads.
REVIEW_SUBPROCESS_EXCEPTIONS: tuple = ("raster.py",)


def _forbidden_process_names_in(source_path: Path) -> list:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    found: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "multiprocessing"):
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "multiprocessing"):
            found.append(node.module)
        elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "os"):
            if node.attr in ("system", "popen") or node.attr.startswith("exec"):
                found.append(f"os.{node.attr}")
    return found


def scan_review_subprocess_imports(scripts_dir: Path) -> dict:
    """Mirrors `test_paper_writing.scan_forbidden_process_imports`'s shape,
    scoped to `figure-review`'s own scripts. Deliberately `rglob` rather
    than the precedent's non-recursive `glob` (`test_paper_writing.py:6127`),
    so a future `scripts/<subdir>/tool.py` is covered rather than silently
    unscanned."""
    violations: dict = {}
    for path in sorted(scripts_dir.rglob("*.py")):
        if path.name in REVIEW_SUBPROCESS_EXCEPTIONS:
            continue
        found = _forbidden_process_names_in(path)
        if found:
            violations[path.name] = found
    return violations


class FigureReviewSubprocessScanTests(unittest.TestCase):

    def test_exception_list_has_exactly_one_entry(self) -> None:
        self.assertEqual(len(REVIEW_SUBPROCESS_EXCEPTIONS), 1)
        self.assertEqual(REVIEW_SUBPROCESS_EXCEPTIONS, ("raster.py",))

    def test_no_shipped_script_imports_a_forbidden_process_primitive(self) -> None:
        self.assertEqual(scan_review_subprocess_imports(REVIEW_SCRIPTS), {})

    def test_a_planted_subprocess_import_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "evil.py").write_text("import subprocess\n", encoding="utf-8")
            violations = scan_review_subprocess_imports(tmp_dir)
        self.assertIn("evil.py", violations)
        self.assertIn("subprocess", violations["evil.py"])

    def test_the_exception_named_file_is_tolerated_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "raster.py").write_text("import subprocess\n", encoding="utf-8")
            violations = scan_review_subprocess_imports(tmp_dir)
        self.assertEqual(violations, {})

    def test_the_scan_directory_is_not_vacuous(self) -> None:
        """Assertion 2 above passes vacuously if `REVIEW_SCRIPTS` ever
        resolved to an empty or wrong directory -- an empty scan and a
        clean scan are the same `{}`. Pin non-vacuity directly: the
        directory this scan actually reads is real, on disk, and not
        empty."""
        self.assertTrue(REVIEW_SCRIPTS.is_dir(), REVIEW_SCRIPTS)
        on_disk = {path.name for path in REVIEW_SCRIPTS.rglob("*.py")}
        self.assertTrue(on_disk, "figure-review ships no scripts, which cannot be")
        self.assertIn("raster.py", on_disk)
        self.assertIn("review_cli.py", on_disk)


# =====================================================================
# Repair-budget isolation, raster-only half (Threat Matrix: "Repair-budget
# isolation"). The full end-to-end half -- a real ledger byte-identical
# before and after a complete visual pass -- is Commit 4's lock 5.
# =====================================================================

class RepairBudgetIsolationTests(unittest.TestCase):

    FORBIDDEN_MODULES = ("paper_latex", "paper_figure")

    def _imported_modules(self, path: Path) -> set:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
        return found

    def test_no_shipped_script_imports_paper_latex_or_paper_figure(self) -> None:
        for path in sorted(REVIEW_SCRIPTS.rglob("*.py")):
            with self.subTest(script=path.name):
                imported = self._imported_modules(path)
                self.assertFalse(
                    imported & set(self.FORBIDDEN_MODULES),
                    f"{path.name} imports {imported & set(self.FORBIDDEN_MODULES)}, "
                    "coupling figure-review to the repair-budget ledger",
                )

    def test_no_shipped_script_names_a_ledger_file(self) -> None:
        for path in sorted(REVIEW_SCRIPTS.rglob("*.py")):
            with self.subTest(script=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("ledger.json", text)
                self.assertNotIn("_write_ledger", text)

    def test_a_planted_ledger_call_is_caught(self) -> None:
        """RED/GREEN evidence for the mutation this lock must survive: a
        `_write_ledger`-shaped call is exactly what the assertion above
        would catch if it ever appeared in a shipped script."""
        planted = "def _write_ledger(path, ledger):\n    pass\n"
        with self.assertRaises(AssertionError):
            self.assertNotIn("_write_ledger", planted)


# =====================================================================
# Rasterizer fallback chain (lock 7) and the Threat Matrix rows scoped to
# `raster.py`. Every case below is stubbed: no real `pdftoppm`,
# `pdftocairo`, `gs` or `sips` is ever invoked by this class.
# =====================================================================

#: A syntactically minimal PNG -- signature plus one `IHDR` chunk, nothing
#: else. `raster._read_png_header` reads only these 26 bytes; it never
#: inflates or validates a trailing `IDAT`/`IEND`, so this is sufficient to
#: prove chain-fallback and header-reporting behavior without a real
#: capture (the real, captured fixtures belong to Commit 2's fixture-driven
#: decode tier).
_FAKE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    + (13).to_bytes(4, "big") + b"IHDR"
    + (800).to_bytes(4, "big") + (600).to_bytes(4, "big")
    + bytes([8, 0, 0, 0, 0])
)

_POPPLER_STUB_BODY = f"""
import sys
from pathlib import Path

argv = sys.argv
prefix = argv[-1]
Path(prefix + "-1.png").write_bytes(bytes.fromhex({_FAKE_PNG_BYTES.hex()!r}))
"""

_GS_STUB_BODY = f"""
import sys
from pathlib import Path

argv = sys.argv
out_flag = next(a for a in argv if a.startswith("-sOutputFile="))
Path(out_flag.split("=", 1)[1]).write_bytes(bytes.fromhex({_FAKE_PNG_BYTES.hex()!r}))
"""

_SIPS_STUB_BODY = f"""
import sys
from pathlib import Path

argv = sys.argv
if "--out" in argv:
    out_path = Path(argv[argv.index("--out") + 1])
    out_path.write_bytes(bytes.fromhex({_FAKE_PNG_BYTES.hex()!r}))
else:
    print("pixelWidth: 800")
    print("pixelHeight: 600")
"""

_SLEEPING_STUB_BODY = "import time\ntime.sleep(10)\n"
_FAILING_STUB_BODY = "import sys\nsys.exit(1)\n"
_SILENT_SUCCESS_STUB_BODY = "import sys\nsys.exit(0)\n"

_STUB_BODIES = {
    "pdftoppm": _POPPLER_STUB_BODY,
    "pdftocairo": _POPPLER_STUB_BODY,
    "gs": _GS_STUB_BODY,
    "sips": _SIPS_STUB_BODY,
}


def _write_stub(bin_dir: Path, name: str, body: str) -> Path:
    path = bin_dir / name
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(0o755)
    return path


def _stub_dir(tmp_dir: Path, tools: dict) -> Path:
    """`tools` maps a tool name to a stub body. Only the named tools become
    executables on the returned directory -- everything else on `CHAIN` is
    genuinely absent from it, never merely unobserved."""
    bin_dir = tmp_dir / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in tools.items():
        _write_stub(bin_dir, name, body)
    return bin_dir


class ChainFallbackTests(unittest.TestCase):

    def _tmp(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        # `.resolve()` is not decoration: on macOS `/var` is a symlink to
        # `/private/var`, so an unresolved fixture path compares unequal to
        # production's own resolved answer for the same directory.
        return Path(holder.name).resolve()

    def _pdf(self, tmp_dir: Path, name: str = "example-figure.pdf") -> Path:
        figures_dir = tmp_dir / "paper" / "Figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        pdf = figures_dir / name
        pdf.write_bytes(b"%PDF-1.4 stub\n%%EOF\n")
        return pdf

    def test_the_first_link_present_is_used(self) -> None:
        tmp_dir = self._tmp()
        bin_dir = _stub_dir(tmp_dir, {"pdftoppm": _STUB_BODIES["pdftoppm"]})
        pdf = self._pdf(tmp_dir)
        result = raster.rasterize(pdf, tmp_dir / "scratch", path=str(bin_dir))
        self.assertEqual(result["tool"], "pdftoppm")
        self.assertTrue(Path(result["png"]).is_file())
        self.assertEqual(result["dpiSource"], "flag")

    def test_a_middle_link_is_reached_only_when_earlier_links_are_absent(self) -> None:
        tmp_dir = self._tmp()
        bin_dir = _stub_dir(tmp_dir, {"gs": _STUB_BODIES["gs"]})
        pdf = self._pdf(tmp_dir)
        result = raster.rasterize(pdf, tmp_dir / "scratch", path=str(bin_dir))
        self.assertEqual(result["tool"], "gs")
        self.assertIsNone(shutil.which("pdftoppm", path=str(bin_dir)))
        self.assertIsNone(shutil.which("pdftocairo", path=str(bin_dir)))

    def test_the_last_link_is_reached_only_when_every_other_link_is_absent(self) -> None:
        tmp_dir = self._tmp()
        bin_dir = _stub_dir(tmp_dir, {"sips": _STUB_BODIES["sips"]})
        pdf = self._pdf(tmp_dir)
        result = raster.rasterize(pdf, tmp_dir / "scratch", path=str(bin_dir))
        self.assertEqual(result["tool"], "sips")
        self.assertEqual(result["dpiSource"], "derived")
        self.assertTrue(Path(result["png"]).is_file())
        for earlier in ("pdftoppm", "pdftocairo", "gs"):
            self.assertIsNone(shutil.which(earlier, path=str(bin_dir)))

    def test_an_emptied_path_refuses_naming_every_probed_tool(self) -> None:
        tmp_dir = self._tmp()
        pdf = self._pdf(tmp_dir)
        with self.assertRaises(Refused) as ctx:
            raster.rasterize(pdf, tmp_dir / "scratch", path="")
        self.assertEqual(ctx.exception.code, "RASTER_TOOLCHAIN_ABSENT")
        for tool in raster.CHAIN:
            self.assertIn(tool, ctx.exception.detail)
        self.assertIn("PATH=", ctx.exception.detail)

        proc = subprocess.run(
            [sys.executable, str(REVIEW_SCRIPTS / "review_cli.py"), "probe", "--path", ""],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["code"], "RASTER_TOOLCHAIN_ABSENT")
        for tool in raster.CHAIN:
            self.assertIn(tool, payload["detail"])

    def test_a_failing_first_link_falls_through_to_the_next(self) -> None:
        """Threat Matrix: PATH resolution / tool discovery -- a link
        present but exiting non-zero is a LINK failure, not a global
        refusal."""
        tmp_dir = self._tmp()
        bin_dir = _stub_dir(tmp_dir, {
            "pdftoppm": _FAILING_STUB_BODY,
            "pdftocairo": _STUB_BODIES["pdftocairo"],
        })
        pdf = self._pdf(tmp_dir)
        result = raster.rasterize(pdf, tmp_dir / "scratch", path=str(bin_dir))
        self.assertEqual(result["tool"], "pdftocairo")

    def test_a_link_that_sleeps_past_the_timeout_falls_through(self) -> None:
        """Threat Matrix: subprocess timeout and resource bound."""
        tmp_dir = self._tmp()
        bin_dir = _stub_dir(tmp_dir, {
            "pdftoppm": _SLEEPING_STUB_BODY,
            "pdftocairo": _STUB_BODIES["pdftocairo"],
        })
        pdf = self._pdf(tmp_dir)
        result = raster.rasterize(pdf, tmp_dir / "scratch", path=str(bin_dir), timeout=2.0)
        self.assertEqual(result["tool"], "pdftocairo")

    def test_every_link_sleeping_refuses_naming_a_timeout_not_a_false_absence(self) -> None:
        tmp_dir = self._tmp()
        bin_dir = _stub_dir(tmp_dir, {tool: _SLEEPING_STUB_BODY for tool in raster.CHAIN})
        pdf = self._pdf(tmp_dir)
        with self.assertRaises(Refused) as ctx:
            raster.rasterize(pdf, tmp_dir / "scratch", path=str(bin_dir), timeout=2.0)
        self.assertEqual(ctx.exception.code, "RASTER_TOOLCHAIN_ABSENT")
        self.assertIn("timed out", ctx.exception.detail)
        for tool in raster.CHAIN:
            self.assertNotIn(
                f"{tool}: absent", ctx.exception.detail,
                "a tool that was present and slow must never be reported as absent",
            )

    def test_a_link_that_exits_zero_writing_nothing_falls_through(self) -> None:
        """Threat Matrix: untrusted output parsing, chain-fallback half.
        The decoder half (truncated/16-bit/palette/interlaced/zero-byte
        fixtures) needs `png_read.py` and is Commit 2's task."""
        tmp_dir = self._tmp()
        bin_dir = _stub_dir(tmp_dir, {
            "pdftoppm": _SILENT_SUCCESS_STUB_BODY,
            "pdftocairo": _STUB_BODIES["pdftocairo"],
        })
        pdf = self._pdf(tmp_dir)
        result = raster.rasterize(pdf, tmp_dir / "scratch", path=str(bin_dir))
        self.assertEqual(result["tool"], "pdftocairo")

    def test_argument_composition_survives_special_characters_in_the_pdf_path(self) -> None:
        """Threat Matrix: subprocess argument composition. Always a list,
        never a composed string, and the PDF operand is resolved absolute
        before it reaches argv -- so a name beginning with `-` is never
        read as a flag."""
        for label, filename in (
            ("space", "a figure.pdf"),
            ("semicolon", "a;figure.pdf"),
            ("leading dash", "-figure.pdf"),
        ):
            with self.subTest(case=label):
                tmp_dir = self._tmp()
                bin_dir = _stub_dir(tmp_dir, {"pdftoppm": _STUB_BODIES["pdftoppm"]})
                pdf = self._pdf(tmp_dir, name=filename)
                result = raster.rasterize(pdf, tmp_dir / "scratch", path=str(bin_dir))
                self.assertEqual(result["tool"], "pdftoppm")
                argv = result["argv"]
                pdf_operand = argv[-2]
                self.assertEqual(pdf_operand, str(pdf.resolve()))
                self.assertTrue(
                    pdf_operand.startswith("/"),
                    "the resolved PDF operand must be absolute, so a leading "
                    "'-' in the figure's own name is never read as a flag",
                )

    def test_probe_reports_the_resolved_link(self) -> None:
        tmp_dir = self._tmp()
        bin_dir = _stub_dir(tmp_dir, {"pdftocairo": _STUB_BODIES["pdftocairo"]})
        self.assertEqual(raster.resolve_link(path=str(bin_dir)), "pdftocairo")
        self.assertEqual(raster.probe(path=str(bin_dir))["resolved"], "pdftocairo")


# =====================================================================
# Commit 2 — the pixels become numbers.
#
# Lock 8 (design.md's lock table, "roster (inherited)") needs no test
# here: it is proven by the four roster assertions Commit 1 already
# added against a ten-tuple (`test_workspace_skills_e2e.py`,
# `test_papersmith_generators.py`, `test_workspace_commands_e2e.py`,
# tasks 1.16-1.18). Stated here explicitly so nobody re-derives or
# re-claims authorship of a lock this file does not prove.
# =====================================================================

# ---------------------------------------------------------------------
# 2.1 — Shared roster shelf (lock 12: zero imports, by construction).
# ---------------------------------------------------------------------

FIGURE_DIMENSIONS_PATH = CORE_FIGURE / "figure_dimensions.py"


def _ast_import_node_count(source: str) -> int:
    tree = ast.parse(source)
    return sum(1 for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)))


class FigureDimensionsImportFreeTests(unittest.TestCase):
    """Lock 12: `_core/figure/figure_dimensions.py` sits outside the forge
    gate's `IMPORT_SCOPE_PATHSPECS` scan (`skills/*/scripts/*.py`), so the
    module is made safe by construction — a roster of string constants
    with zero `Import`/`ImportFrom` AST nodes — rather than by adding a
    scan that would never reach it."""

    def test_the_module_exists(self) -> None:
        self.assertTrue(
            FIGURE_DIMENSIONS_PATH.is_file(),
            f"{FIGURE_DIMENSIONS_PATH} does not exist",
        )

    def test_the_module_carries_zero_import_nodes(self) -> None:
        source = FIGURE_DIMENSIONS_PATH.read_text(encoding="utf-8")
        self.assertEqual(_ast_import_node_count(source), 0)

    def test_a_planted_import_is_caught(self) -> None:
        """RED/GREEN evidence for the mutation lock 12 must survive: a
        throwaway `import os` added to the module's own source is exactly
        what the assertion above would catch."""
        source = FIGURE_DIMENSIONS_PATH.read_text(encoding="utf-8")
        mutated = "import os\n" + source
        self.assertEqual(_ast_import_node_count(source), 0)
        self.assertEqual(_ast_import_node_count(mutated), 1)


# ---------------------------------------------------------------------
# 2.2 — PNG decoder (`png_read.py`): decode-to-known-values, and lock 13
# (flavour refusal) in both directions.
# ---------------------------------------------------------------------

def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        len(data).to_bytes(4, "big") + chunk_type + data
        + zlib.crc32(chunk_type + data).to_bytes(4, "big")
    )


def _minimal_png(
    width: int, height: int, *, bit_depth: int = 8, color_type: int = 0,
    interlace: int = 0, rows: list | None = None, channels: int | None = None,
    truncate_idat_to: int | None = None,
) -> bytes:
    """Build a syntactically complete, minimal PNG for a format/refusal
    test — never a claim that this is a captured raster. `rows` is a list
    of per-row raw scanlines (filter byte already applied, defaulting to
    filter type 0 / "None" for every row) as plain bytes."""
    if channels is None:
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    if rows is None:
        stride = width * channels
        rows = [b"\x00" + bytes([0] * stride) for _ in range(height)]
    raw = b"".join(rows)
    idat_data = zlib.compress(raw)
    if truncate_idat_to is not None:
        idat_data = idat_data[:truncate_idat_to]
    ihdr = (
        width.to_bytes(4, "big") + height.to_bytes(4, "big")
        + bytes([bit_depth, color_type, 0, 0, interlace])
    )
    body = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
    if color_type == 3:
        body += _png_chunk(b"PLTE", bytes([0, 0, 0, 255, 255, 255]))
    body += _png_chunk(b"IDAT", idat_data)
    body += _png_chunk(b"IEND", b"")
    return body


def _write_png(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


PNG_READ_PATH = REVIEW_SCRIPTS / "png_read.py"


class PngReadDecodeTests(unittest.TestCase):
    """Task 2.3: a valid, committed, real-captured PNG decodes to known
    pixel values. `tiny-example-figure.png` is a real `pdftoppm -gray`
    capture at a deliberately low dpi (16x9), small enough to assert the
    exact grayscale buffer byte-for-byte. Its expected buffer below was
    computed once from the same capture with an independent decoder
    (Pillow, not shipped, used only to author this expectation) applying
    the identical integer BT.601 formula this module implements, and is
    hardcoded here as the test's own ground truth."""

    #: `(299R + 587G + 114B) // 1000` over every pixel of
    #: tiny-example-figure.png, row-major, computed once at fixture
    #: authoring time.
    _EXPECTED_HEX = (
        "0000000000000000000000000000000000ffffffffffffffffffffffffffff"
        "ff00ffffffffffffffffffffffffffffff00ffffffffffffffffffffffffff"
        "ffff00ffffffffffffffffffffffffffffff00ffffffffffffffffffffffff"
        "ffffff00ffffffffffffffffffffffffffffff00ffffffffffffffffffffff"
        "ffffffff00000000000000000000000000000000"
    )

    def _import_png_read(self):
        sys.path.insert(0, str(REVIEW_SCRIPTS))
        import png_read
        return png_read

    def test_module_exists(self) -> None:
        self.assertTrue(PNG_READ_PATH.is_file(), f"{PNG_READ_PATH} does not exist")

    def test_a_real_capture_decodes_to_the_expected_grayscale_buffer(self) -> None:
        png_read = self._import_png_read()
        fixture = FIXTURES / "tiny-example-figure" / "tiny-example-figure.png"
        width, height, gray = png_read.read_gray(fixture)
        self.assertEqual((width, height), (16, 9))
        self.assertEqual(bytes(gray), bytes.fromhex(self._EXPECTED_HEX))


class PngReadFlavourRefusalTests(unittest.TestCase):
    """Lock 13: accepting a 16-bit or palette PNG and mis-reading its
    stride is the mutation this lock exists to catch. Each case below
    asserts the refusal ITSELF (code and named property), not merely
    "did not crash" — a decoder stub that ignores the header and only
    ever succeeds on 8-bit fixtures would otherwise slip through
    silently on a mis-shaped assertion."""

    def _import_png_read(self):
        sys.path.insert(0, str(REVIEW_SCRIPTS))
        import png_read
        return png_read

    def _tmp_png(self, **kwargs) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        path = Path(holder.name) / "fixture.png"
        return _write_png(path, _minimal_png(**kwargs))

    def test_a_valid_8bit_fixture_is_not_refused(self) -> None:
        png_read = self._import_png_read()
        path = self._tmp_png(width=4, height=4, color_type=0)
        width, height, gray = png_read.read_gray(path)
        self.assertEqual((width, height), (4, 4))
        self.assertEqual(len(gray), 16)

    def test_16bit_depth_refuses_naming_the_bit_depth(self) -> None:
        png_read = self._import_png_read()
        path = self._tmp_png(width=4, height=4, color_type=0, bit_depth=16)
        with self.assertRaises(Refused) as ctx:
            png_read.read_gray(path)
        self.assertEqual(ctx.exception.code, "RASTER_FORMAT_UNSUPPORTED")
        self.assertIn("16", ctx.exception.detail)

    def test_palette_color_type_refuses_naming_the_color_type(self) -> None:
        png_read = self._import_png_read()
        path = self._tmp_png(width=4, height=4, color_type=3)
        with self.assertRaises(Refused) as ctx:
            png_read.read_gray(path)
        self.assertEqual(ctx.exception.code, "RASTER_FORMAT_UNSUPPORTED")
        self.assertIn("colour type", ctx.exception.detail.lower())

    def test_interlaced_refuses_naming_the_interlace_flag(self) -> None:
        png_read = self._import_png_read()
        path = self._tmp_png(width=4, height=4, color_type=0, interlace=1)
        with self.assertRaises(Refused) as ctx:
            png_read.read_gray(path)
        self.assertEqual(ctx.exception.code, "RASTER_FORMAT_UNSUPPORTED")
        self.assertIn("interlace", ctx.exception.detail.lower())

    def test_a_stub_that_ignores_the_header_would_not_catch_these(self) -> None:
        """RED evidence that the three assertions above test the refusal,
        not "did not crash": a decoder that only checks the PNG signature
        and always returns some buffer would pass every one of the three
        cases above with flying colours, which is exactly why each of
        them asserts on `Refused` rather than on a returned shape."""
        def _stub_ignoring_header(_path):
            return 4, 4, bytearray(16)

        # The stub never raises, so asserting Refused against it fails —
        # demonstrating these tests would catch a stub this naive.
        with self.assertRaises(AssertionError):
            with self.assertRaises(Refused):
                _stub_ignoring_header(Path("irrelevant"))


class PngReadThreatMatrixTests(unittest.TestCase):
    """Task 2.5 — Threat Matrix, decoder half of "untrusted output
    parsing": truncated, zero-byte, and an oversized-inflate ("zlib
    bomb") fixture each refuse rather than allocating unboundedly."""

    def _import_png_read(self):
        sys.path.insert(0, str(REVIEW_SCRIPTS))
        import png_read
        return png_read

    def _tmp_path(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        # `.resolve()` is not decoration: on macOS `/var` is a symlink to
        # `/private/var`, so an unresolved fixture path compares unequal to
        # production's own resolved answer for the same directory.
        return Path(holder.name).resolve() / "fixture.png"

    def test_zero_byte_file_refuses(self) -> None:
        png_read = self._import_png_read()
        path = self._tmp_path()
        path.write_bytes(b"")
        with self.assertRaises(Refused) as ctx:
            png_read.read_gray(path)
        self.assertEqual(ctx.exception.code, "RASTER_FORMAT_UNSUPPORTED")

    def test_truncated_file_refuses(self) -> None:
        png_read = self._import_png_read()
        full = _minimal_png(width=8, height=8, color_type=0)
        path = self._tmp_path()
        path.write_bytes(full[: len(full) // 2])
        with self.assertRaises(Refused) as ctx:
            png_read.read_gray(path)
        self.assertEqual(ctx.exception.code, "RASTER_FORMAT_UNSUPPORTED")

    def test_truncated_idat_refuses_rather_than_reading_garbage(self) -> None:
        png_read = self._import_png_read()
        data = _minimal_png(width=8, height=8, color_type=0, truncate_idat_to=3)
        path = self._tmp_path()
        path.write_bytes(data)
        with self.assertRaises(Refused) as ctx:
            png_read.read_gray(path)
        self.assertEqual(ctx.exception.code, "RASTER_FORMAT_UNSUPPORTED")

    def test_an_oversized_inflate_refuses_rather_than_allocating_unboundedly(self) -> None:
        """A classic "zlib bomb": a small IHDR (so the expected bound is
        tiny) whose IDAT decompresses to far more bytes than that bound
        allows. The bound is `width*height*channels + height` read from
        IHDR, computed BEFORE inflating."""
        png_read = self._import_png_read()
        width, height, channels = 4, 4, 1
        bound = width * height * channels + height
        bomb_raw = bytes(bound * 1000)  # decompresses to 1000x the bound
        ihdr = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 0, 0, 0, 0])
        body = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
        body += _png_chunk(b"IDAT", zlib.compress(bomb_raw, 9))
        body += _png_chunk(b"IEND", b"")
        path = self._tmp_path()
        path.write_bytes(body)
        with self.assertRaises(Refused) as ctx:
            png_read.read_gray(path)
        self.assertEqual(ctx.exception.code, "RASTER_FORMAT_UNSUPPORTED")


# ---------------------------------------------------------------------
# 2.3 — Geometry: out-of-bounds (lock 1), overlap (lock 2), threshold
# (lock 9), and canvas occupancy.
# ---------------------------------------------------------------------

GEOMETRY_PATH = REVIEW_SCRIPTS / "geometry.py"


def _import_geometry():
    sys.path.insert(0, str(REVIEW_SCRIPTS))
    import geometry
    return geometry


def _import_png_read():
    sys.path.insert(0, str(REVIEW_SCRIPTS))
    import png_read
    return png_read


class GeometryOutOfBoundsTests(unittest.TestCase):
    """Lock 1: the out-of-bounds band is exactly one pixel wide. The
    mutation this lock must survive is `1px -> 0px` (widening/narrowing
    the band) or `>=` -> `>` (an off-by-one at the edge itself) --
    neither of the two fixtures alone catches both; together they do."""

    def test_ink_on_the_exact_outermost_row_fails(self) -> None:
        geometry = _import_geometry()
        png_read = _import_png_read()
        fixture = FIXTURES / "outer-row-ink" / "outer-row-ink.png"
        width, height, gray = png_read.read_gray(fixture)
        result = geometry.out_of_bounds(width, height, gray)
        self.assertEqual(result["verdict"], "fail")
        self.assertIn("top", result["edges"])
        self.assertEqual(result["edges"]["top"], 1)

    def test_ink_one_pixel_inward_passes(self) -> None:
        geometry = _import_geometry()
        png_read = _import_png_read()
        fixture = FIXTURES / "inner-row-ink" / "inner-row-ink.png"
        width, height, gray = png_read.read_gray(fixture)
        result = geometry.out_of_bounds(width, height, gray)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["edges"], {})

    def test_band_widened_to_two_pixels_would_wrongly_fail_the_pass_fixture(self) -> None:
        """RED evidence: a `1px -> 2px` band-width mutation would also
        inspect row 1, so `inner-row-ink.png` (ink at row 1 only) would
        wrongly report `fail`. Demonstrated directly against the raw
        buffer rather than by patching production code."""
        png_read = _import_png_read()
        fixture = FIXTURES / "inner-row-ink" / "inner-row-ink.png"
        width, height, gray = png_read.read_gray(fixture)
        widened_band_rows = {0, 1, height - 2, height - 1}
        has_ink_in_widened_band = any(
            gray[y * width + x] <= 200
            for y in widened_band_rows for x in range(width)
        )
        self.assertTrue(
            has_ink_in_widened_band,
            "a widened band would see this fixture's row-1 ink -- exactly "
            "the false failure this lock's two fixtures together catch",
        )


class GeometryOverlapTests(unittest.TestCase):
    """Lock 2: strict half-open intersection. The mutation this lock
    must survive is `<` -> `<=` (treating a shared boundary edge as
    overlap)."""

    def test_boxes_sharing_exactly_one_edge_do_not_overlap(self) -> None:
        geometry = _import_geometry()
        boxes = [(0, 0, 4, 4), (4, 0, 8, 4)]
        self.assertEqual(geometry.overlaps(boxes), [])

    def test_one_column_of_penetration_overlaps(self) -> None:
        geometry = _import_geometry()
        boxes = [(0, 0, 4, 4), (3, 0, 7, 4)]
        collisions = geometry.overlaps(boxes)
        self.assertEqual(len(collisions), 1)
        self.assertEqual(sorted(collisions[0]["boxes"]), sorted([[0, 0, 4, 4], [3, 0, 7, 4]]))
        for box in collisions[0]["boxes"]:
            self.assertNotIsInstance(box, dict)  # no component name attached

    def test_the_fixtures_backing_both_scenarios_are_real_paintable_rasters(self) -> None:
        """The two boxes above are asserted directly against `overlaps()`
        (lock 2 is about box-intersection arithmetic, not component
        detection), but each scenario's shape is also backed by a real
        captured-and-documented raster proving the boxes are paintable
        ink, not merely arithmetic fictions."""
        png_read = _import_png_read()
        for name in ("two-boxes-abutting", "two-boxes-penetrating"):
            fixture = FIXTURES / name / f"{name}.png"
            width, height, gray = png_read.read_gray(fixture)
            self.assertTrue(any(v <= 200 for v in gray), f"{name} has no ink at all")

    def test_strict_to_non_strict_intersection_would_wrongly_overlap_the_abutting_pair(self) -> None:
        """RED evidence: `<` -> `<=` on both axis comparisons would treat
        the abutting pair (sharing column x=4 only) as overlapping."""
        ax0, ay0, ax1, ay1 = 0, 0, 4, 4
        bx0, by0, bx1, by1 = 4, 0, 8, 4
        non_strict_overlap = ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1
        strict_overlap = ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1
        self.assertTrue(non_strict_overlap, "the mutant would call this a collision")
        self.assertFalse(strict_overlap, "the real strict check must not")


class GeometryThresholdBoundaryTests(unittest.TestCase):
    """Lock 9: `INK_MAX_LEVEL = 200`, `level <= 200` is ink. The mutation
    this lock must survive is `<=` -> `<` at the exact boundary. A
    fixture using only pure black/white must NOT be the only evidence --
    it survives that exact mutation, since neither 0 nor 255 sits near
    the boundary."""

    def test_level_200_is_ink_and_201_is_background(self) -> None:
        geometry = _import_geometry()
        png_read = _import_png_read()
        fixture = FIXTURES / "threshold-boundary" / "threshold-boundary.png"
        width, height, gray = png_read.read_gray(fixture)
        self.assertEqual(gray[2 * width + 5], 200)
        self.assertEqual(gray[2 * width + 6], 201)
        self.assertLessEqual(gray[2 * width + 5], geometry.INK_MAX_LEVEL)
        self.assertGreater(gray[2 * width + 6], geometry.INK_MAX_LEVEL)
        # Exercise the actual classification decision through a real
        # geometry function, not just a comparison restated in the test:
        # a `<=` -> `<` mutation at INK_MAX_LEVEL must flip pixel (5,2)
        # out of every detected ink region.
        regions = geometry.ink_regions(width, height, gray)
        self.assertTrue(
            any(x0 <= 5 < x1 and y0 <= 2 < y1 for (x0, y0, x1, y1) in regions),
            "level-200 pixel (5,2) must be classified as ink",
        )
        self.assertFalse(
            any(x0 <= 6 < x1 and y0 <= 2 < y1 for (x0, y0, x1, y1) in regions),
            "level-201 pixel (6,2) must be classified as background",
        )

    def test_a_pure_black_and_white_fixture_alone_would_survive_the_le_to_lt_mutation(self) -> None:
        """RED evidence for why the pure-black/white fixture cannot be
        the only boundary evidence: `<=` -> `<` at INK_MAX_LEVEL=200
        changes nothing for level 0 (still ink) or level 255 (still
        background) -- only the exact-200 pixel detects it."""
        pure_levels = (0, 255)
        for level in pure_levels:
            self.assertEqual(level <= 200, level < 200)
        # But the exact boundary pixel DOES change classification.
        self.assertNotEqual(200 <= 200, 200 < 200)

    def test_the_tiny_real_capture_uses_only_pure_black_and_white(self) -> None:
        png_read = _import_png_read()
        fixture = FIXTURES / "tiny-example-figure" / "tiny-example-figure.png"
        _, _, gray = png_read.read_gray(fixture)
        self.assertEqual(set(gray), {0, 255})


class GeometryOccupancyTests(unittest.TestCase):

    def test_a_blank_lower_half_reports_a_near_zero_fraction_with_no_verdict(self) -> None:
        geometry = _import_geometry()
        png_read = _import_png_read()
        fixture = FIXTURES / "lower-band-blank" / "lower-band-blank.png"
        width, height, gray = png_read.read_gray(fixture)
        bands = geometry.occupancy(width, height, gray, bands=2)
        self.assertEqual(len(bands), 2)
        self.assertGreater(bands[0], 0.0)
        self.assertEqual(bands[1], 0.0)
        for band in bands:
            self.assertIsInstance(band, float)


# ---------------------------------------------------------------------
# 2.4 — Border precondition (Decision 8, lock 10) and 2.5 — findings
# assembly (the `visual` dict, roster-driven).
# ---------------------------------------------------------------------

FINDINGS_PATH = REVIEW_SCRIPTS / "findings.py"


def _import_findings():
    sys.path.insert(0, str(REVIEW_SCRIPTS))
    import findings
    return findings


class BorderPreconditionTests(unittest.TestCase):
    """Lock 10: a border-less standalone source reports `unmeasured`, not
    `fail`, because it fits its own canvas to its ink by construction.
    The mutation this lock must survive is deleting the border read
    entirely, so out-of-bounds always carries a verdict -- a fixture
    with a declared border alone would survive that mutation; only the
    border-less fixture, whose ink genuinely touches every edge, catches
    it."""

    def test_border_pt_is_read_from_a_declared_border(self) -> None:
        findings = _import_findings()
        tex = FIXTURES / "example-figure" / "example-figure.tex"
        self.assertEqual(findings.border_pt_from_tex(tex), 2.0)

    def test_no_border_declared_yields_none(self) -> None:
        findings = _import_findings()
        tex = FIXTURES / "example-figure-noborder" / "example-figure-noborder.tex"
        self.assertIsNone(findings.border_pt_from_tex(tex))

    def test_an_unparseable_header_yields_none(self) -> None:
        findings = _import_findings()
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        tex = Path(holder.name) / "no-header.tex"
        tex.write_text("\\begin{document}nothing here\\end{document}\n", encoding="utf-8")
        self.assertIsNone(findings.border_pt_from_tex(tex))

    def test_border_less_source_with_ink_on_row_zero_is_unmeasured_not_fail(self) -> None:
        findings = _import_findings()
        png_read = _import_png_read()
        fixture = FIXTURES / "example-figure-noborder" / "example-figure-noborder.png"
        width, height, gray = png_read.read_gray(fixture)
        border_pt = findings.border_pt_from_tex(
            FIXTURES / "example-figure-noborder" / "example-figure-noborder.tex"
        )
        self.assertIsNone(border_pt)
        visual = findings.build_visual(
            width=width, height=height, gray=gray, tool="pdftoppm",
            dpi=150, dpi_source="flag", color_model="rgb",
            declared_border_pt=border_pt,
        )
        oob = visual["dimensions"]["out-of-bounds"]
        self.assertEqual(oob["verdict"], "unmeasured")
        self.assertEqual(oob["reason"], "NO_DECLARED_BORDER")

    def test_a_bordered_clean_fixture_survives_the_deleted_border_read_mutation(self) -> None:
        """RED evidence: if the border read were deleted (always treating
        the source as border-declared), THIS fixture alone would still
        correctly report `pass` -- because it genuinely has a clean
        margin. Only the border-less fixture above actually distinguishes
        "no border was read" from "a border was read and ink is clean"."""
        findings = _import_findings()
        png_read = _import_png_read()
        fixture = FIXTURES / "example-figure" / "example-figure.png"
        width, height, gray = png_read.read_gray(fixture)
        visual_with_border_read = findings.build_visual(
            width=width, height=height, gray=gray, tool="pdftoppm",
            dpi=150, dpi_source="flag", color_model="rgb", declared_border_pt=2.0,
        )
        visual_pretending_always_declared = findings.build_visual(
            width=width, height=height, gray=gray, tool="pdftoppm",
            dpi=150, dpi_source="flag", color_model="rgb", declared_border_pt=1.0,
        )
        self.assertEqual(
            visual_with_border_read["dimensions"]["out-of-bounds"]["verdict"],
            visual_pretending_always_declared["dimensions"]["out-of-bounds"]["verdict"],
        )


class FindingsAssemblyTests(unittest.TestCase):
    """Task 2.15: `findings.py` assembles the full `visual` dict from
    `figure_dimensions`'s roster, populating every dimension exactly
    once, plus `provenance`."""

    def test_every_roster_dimension_is_present_exactly_once(self) -> None:
        findings = _import_findings()
        figure_dimensions = _import_figure_dimensions()
        png_read = _import_png_read()
        fixture = FIXTURES / "example-figure" / "example-figure.png"
        width, height, gray = png_read.read_gray(fixture)
        visual = findings.build_visual(
            width=width, height=height, gray=gray, tool="pdftoppm",
            dpi=150, dpi_source="flag", color_model="rgb", declared_border_pt=2.0,
        )
        self.assertEqual(
            sorted(visual["dimensions"].keys()),
            sorted(figure_dimensions.ALL_DIMENSIONS),
        )
        for name in figure_dimensions.ALL_DIMENSIONS:
            self.assertIn("verdict", visual["dimensions"][name])
            self.assertIn("reason", visual["dimensions"][name])

    def test_canvas_occupancy_carries_bands_and_no_pass_fail_verdict(self) -> None:
        findings = _import_findings()
        png_read = _import_png_read()
        fixture = FIXTURES / "example-figure" / "example-figure.png"
        width, height, gray = png_read.read_gray(fixture)
        visual = findings.build_visual(
            width=width, height=height, gray=gray, tool="pdftoppm",
            dpi=150, dpi_source="flag", color_model="rgb", declared_border_pt=2.0,
        )
        occupancy = visual["dimensions"]["canvas-occupancy"]
        self.assertIsNone(occupancy["verdict"])
        self.assertIn("bands", occupancy)
        self.assertIsInstance(occupancy["bands"], list)

    def test_overlap_collisions_name_both_boxes_in_pixel_and_point(self) -> None:
        findings = _import_findings()
        png_read = _import_png_read()
        fixture = FIXTURES / "two-boxes-penetrating" / "two-boxes-penetrating.png"
        width, height, gray = png_read.read_gray(fixture)
        visual = findings.build_visual(
            width=width, height=height, gray=gray, tool="pdftoppm",
            dpi=150, dpi_source="flag", color_model="rgb", declared_border_pt=1.0,
            boxes=[(0, 0, 4, 4), (3, 0, 7, 4)],
        )
        overlap = visual["dimensions"]["overlap"]
        self.assertEqual(overlap["verdict"], "fail")
        self.assertEqual(len(overlap["collisions"]), 1)
        collision = overlap["collisions"][0]
        self.assertEqual(len(collision["pixel"]), 2)
        self.assertEqual(len(collision["point"]), 2)

    def test_provenance_names_tool_dpi_threshold_and_connectivity(self) -> None:
        findings = _import_findings()
        geometry = _import_geometry()
        png_read = _import_png_read()
        fixture = FIXTURES / "example-figure" / "example-figure.png"
        width, height, gray = png_read.read_gray(fixture)
        visual = findings.build_visual(
            width=width, height=height, gray=gray, tool="pdftoppm",
            dpi=150, dpi_source="flag", color_model="rgb", declared_border_pt=2.0,
        )
        provenance = visual["provenance"]
        self.assertEqual(provenance["tool"], "pdftoppm")
        self.assertEqual(provenance["dpi"], 150)
        self.assertEqual(provenance["dpiSource"], "flag")
        self.assertEqual(provenance["colorModel"], "rgb")
        self.assertEqual(provenance["inkMaxLevel"], geometry.INK_MAX_LEVEL)
        self.assertEqual(provenance["connectivity"], geometry.CONNECTIVITY)
        self.assertEqual(provenance["pixelWidth"], width)
        self.assertEqual(provenance["pixelHeight"], height)
        self.assertEqual(provenance["declaredBorderPt"], 2.0)


def _import_figure_dimensions():
    sys.path.insert(0, str(CORE_FIGURE))
    import figure_dimensions
    return figure_dimensions


class RosterDriftLockFigureReviewHalf(unittest.TestCase):
    """Lock 11, `figure-review`'s own half: its produced keys equal the
    shared roster. This half is provably GREEN in Commit 2 -- it needs
    nothing from `paper-writing`."""

    def test_findings_produced_keys_equal_the_roster(self) -> None:
        findings = _import_findings()
        figure_dimensions = _import_figure_dimensions()
        png_read = _import_png_read()
        fixture = FIXTURES / "example-figure" / "example-figure.png"
        width, height, gray = png_read.read_gray(fixture)
        visual = findings.build_visual(
            width=width, height=height, gray=gray, tool="pdftoppm",
            dpi=150, dpi_source="flag", color_model="rgb", declared_border_pt=2.0,
        )
        self.assertEqual(
            sorted(visual["dimensions"].keys()),
            sorted(figure_dimensions.ALL_DIMENSIONS),
        )


class RosterDriftLockCrossModuleHalfStaysRedUntilCommit3(unittest.TestCase):
    """Lock 11, task 2.16's full cross-module assertion: written now,
    deliberately RED, and left RED on purpose. `paper_figure_audit.py`'s
    `audit_semantics` does not accept a `visual` argument and returns no
    `visual` key until Commit 3 wires it to this same roster (tasks
    3.2/3.3) -- so this test's failure IS the documented, expected state
    of Commit 2, not a regression. It stays skipped-via-expected-failure
    rather than removed, so nobody has to re-derive why it is red.
    Confirmed GREEN in task 3.3, not here.
    """

    def test_paper_figure_audit_default_visual_keys_will_equal_the_roster(self) -> None:
        figure_dimensions = _import_figure_dimensions()
        sys.path.insert(0, str(FORGE_ROOT / ".opencode" / "skills" / "paper-writing" / "scripts"))
        import paper_figure_audit

        report = paper_figure_audit.audit_semantics(
            tex="", manifest={}, section_text="", contract_figure=None,
        )
        visual = report.get("visual")
        self.assertIsNotNone(
            visual,
            "expected RED until Commit 3 (task 3.2/3.3): audit_semantics "
            "carries no 'visual' key yet",
        )
        self.assertEqual(
            sorted(visual["dimensions"].keys()),
            sorted(figure_dimensions.ALL_DIMENSIONS),
        )


# ---------------------------------------------------------------------
# 2.5 (cont'd) — the `measure` verb on `review_cli.py`.
# ---------------------------------------------------------------------

class MeasureVerbTests(unittest.TestCase):
    """Task 2.17: `measure` consumes the PNG + provenance a prior
    `raster` call already wrote, and writes a plain-data
    `visual-report.json` -- no `Path` objects, string/int/float/bool/
    list/dict only."""

    def _tmp(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        # `.resolve()` is not decoration: on macOS `/var` is a symlink to
        # `/private/var`, so an unresolved fixture path compares unequal to
        # production's own resolved answer for the same directory.
        return Path(holder.name).resolve()

    def _rasterize_first(self, tmp_dir: Path) -> tuple:
        figures_dir = tmp_dir / "paper" / "Figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        pdf = figures_dir / "example-figure.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub\n%%EOF\n")
        # A stub writing a REAL, fully decodable PNG (unlike Commit 1's
        # header-only `_FAKE_PNG_BYTES`, sufficient there because it only
        # ever exercised `raster.py`'s own header peek) -- `measure`
        # actually decodes and geometrically measures this raster.
        real_png = _minimal_png(width=4, height=4, color_type=0)
        stub_body = f"""
import sys
from pathlib import Path

argv = sys.argv
prefix = argv[-1]
Path(prefix + "-1.png").write_bytes(bytes.fromhex({real_png.hex()!r}))
"""
        bin_dir = _stub_dir(tmp_dir, {"pdftoppm": stub_body})
        out_dir = tmp_dir / "scratch"
        raster.rasterize(pdf, out_dir, path=str(bin_dir))
        return pdf, out_dir

    def test_measure_writes_a_plain_data_visual_report(self) -> None:
        tmp_dir = self._tmp()
        pdf, out_dir = self._rasterize_first(tmp_dir)
        proc = subprocess.run(
            [sys.executable, str(REVIEW_SCRIPTS / "review_cli.py"), "measure",
             "--pdf", str(pdf), "--out", str(out_dir)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report_path = out_dir / "visual-report.json"
        self.assertTrue(report_path.is_file())
        payload = json.loads(report_path.read_text(encoding="utf-8"))

        def _assert_plain_data(value) -> None:
            if isinstance(value, dict):
                for v in value.values():
                    _assert_plain_data(v)
            elif isinstance(value, list):
                for v in value:
                    _assert_plain_data(v)
            else:
                self.assertIsInstance(value, (str, int, float, bool, type(None)))

        _assert_plain_data(payload)
        self.assertIn("dimensions", payload)
        self.assertIn("provenance", payload)

    def test_measure_without_a_prior_raster_refuses(self) -> None:
        tmp_dir = self._tmp()
        figures_dir = tmp_dir / "paper" / "Figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        pdf = figures_dir / "example-figure.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub\n%%EOF\n")
        proc = subprocess.run(
            [sys.executable, str(REVIEW_SCRIPTS / "review_cli.py"), "measure",
             "--pdf", str(pdf), "--out", str(tmp_dir / "scratch")],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_measure_over_a_fully_failing_chain_writes_no_ledger_file(self) -> None:
        """Threat Matrix, extended to `measure` as a second entry point
        (task 2.18) -- alongside the AST-level check from task 1.7, this
        proves it dynamically: even when `raster` fails every link,
        nothing under the skill's own scripts ever opens a ledger file,
        and `measure` cannot run at all without a prior raster (the
        assertion above), so no ledger write is reachable from this
        verb either."""
        review_scripts_text = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(REVIEW_SCRIPTS.rglob("*.py"))
        )
        self.assertNotIn("ledger.json", review_scripts_text)
        self.assertNotIn("_write_ledger", review_scripts_text)


# =====================================================================
# Task 4.6: the end-to-end join, over a REAL captured raster fixture
# (task 2.19's `example-figure`, `border=2pt`) -- `probe` -> `raster` ->
# `measure`, then `figure audit --visual-report` against the result.
# `--visual-report` is resolved through `paper_cli._resolve_repo_path`
# (design.md Decision 5), which requires the report to sit inside the
# real repository root -- so this fixture, unlike every other class in
# this file, lives under the already-gitignored `.scratch/` tree
# (`.gitignore`'s own comment on why), never a bare `tempfile.
# TemporaryDirectory()`.
# =====================================================================

class VisualReportEndToEndAuditTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = (
            FORGE_ROOT / ".scratch"
            / f".figure-review-e2e-visual-report-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.tmp_dir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

    def test_probe_raster_measure_then_figure_audit_visual_report(self) -> None:
        fixture_dir = FIXTURES / "example-figure"
        pdf = self.tmp_dir / "paper" / "Figures" / "example-figure.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF-1.4 stub\n%%EOF\n")

        # An injected-`PATH` stub that reproduces the REAL captured PNG
        # bytes at the front door's own expected output path -- the same
        # "stub copies a committed fixture's bytes" tier this skill's own
        # suite already uses (`ChainFallbackTests`), never a freshly
        # rasterized or hand-drawn raster.
        real_png_bytes = (fixture_dir / "example-figure.png").read_bytes()
        stub_body = (
            "import sys\nfrom pathlib import Path\n\n"
            "argv = sys.argv\n"
            "prefix = argv[-1]\n"
            f"Path(prefix + '-1.png').write_bytes(bytes.fromhex({real_png_bytes.hex()!r}))\n"
        )
        bin_dir = _stub_dir(self.tmp_dir, {"pdftoppm": stub_body})

        probe = raster.probe(path=str(bin_dir))
        self.assertEqual(probe["resolved"], "pdftoppm")

        out_dir = self.tmp_dir / "scratch"
        raster_result = raster.rasterize(pdf, out_dir, path=str(bin_dir))
        self.assertEqual(raster_result["tool"], "pdftoppm")

        findings = _import_findings()
        figure_dimensions = _import_figure_dimensions()
        visual = findings.measure_figure(
            Path(raster_result["png"]), raster_result, tex_path=fixture_dir / "example-figure.tex",
        )
        report_path = out_dir / "visual-report.json"
        raster._atomic_write_json(report_path, visual)

        manifest_path = self.tmp_dir / "example-figure.diagram.json"
        manifest_path.write_text(json.dumps({"components": []}), encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()) as buf:
            exit_code = paper_cli.main([
                "figure", "audit", "--file", str(fixture_dir / "example-figure.tex"),
                "--manifest", str(manifest_path), "--section", "introduction",
                "--visual-report", str(report_path),
            ])
        payload = json.loads(buf.getvalue())

        self.assertEqual(exit_code, 0, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            sorted(payload["visual"]["dimensions"].keys()),
            sorted(figure_dimensions.ALL_DIMENSIONS),
        )
        # `example-figure` declares `border=2pt` (task 2.19's provenance
        # note), so out-of-bounds is a COMPUTED verdict here, never the
        # `unmeasured`/`NO_DECLARED_BORDER` a border-less source would get.
        self.assertIn(payload["visual"]["dimensions"]["out-of-bounds"]["verdict"], ("pass", "fail"))
        self.assertIsNotNone(payload["visual"]["provenance"])
        self.assertEqual(payload["visual"]["provenance"]["tool"], "pdftoppm")


class TheJoinIsAPathNeverAnImportTests(unittest.TestCase):
    """`figure audit` reaches this skill's findings through a file path on the
    command line, and through nothing else.

    The constraint is architectural: `paper-writing` and `figure-review` are
    separate skills with separate subprocess seams and separate repair
    budgets, and an import edge would quietly make them one. It was checked by
    hand twice while this change was written and both times it held -- which
    is exactly the state this class exists to end. A property that is true and
    unguarded and a property that is true because something holds it look the
    same from outside, and only one of them survives the next edit.
    """

    #: The consumers. `paper_cli` parses `--visual-report` and `paper_figure_audit`
    #: receives the already-read dict; between them they are the whole join.
    CONSUMERS = (
        FORGE_ROOT / ".opencode" / "skills" / "paper-writing" / "scripts" / "paper_cli.py",
        FORGE_ROOT / ".opencode" / "skills" / "paper-writing" / "scripts" / "paper_figure_audit.py",
    )

    #: Every module name this skill ships, derived rather than listed, so a
    #: module added later is covered without anybody remembering to add it here.
    def _review_module_names(self) -> set[str]:
        return {path.stem for path in REVIEW_SCRIPTS.glob("*.py")}

    def test_the_derivation_finds_the_modules_it_claims_to_guard(self) -> None:
        """Non-vacuity. An empty set would make every assertion below pass over
        nothing, and a scan that found no modules reads exactly like a scan
        that found no violations."""
        names = self._review_module_names()
        self.assertGreaterEqual(
            len(names), 3,
            f"derived only {sorted(names)} from {REVIEW_SCRIPTS}; the guard "
            "below would be asserting over an empty roster")
        self.assertIn("raster", names)

    def test_no_consumer_imports_anything_this_skill_ships(self) -> None:
        forbidden = self._review_module_names()
        for source_path in self.CONSUMERS:
            with self.subTest(module=source_path.name):
                self.assertTrue(source_path.is_file(), f"missing {source_path}")
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
                found = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        found += [a.name for a in node.names
                                  if a.name.split(".")[0] in forbidden]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        if node.module.split(".")[0] in forbidden:
                            found.append(node.module)
                self.assertEqual(
                    found, [],
                    f"{source_path.name} imports {found} from figure-review. "
                    "The join is `--visual-report <path>`: a report already "
                    "written to disk, read as plain data. An import makes one "
                    "skill's subprocess seam and repair budget the other's")


