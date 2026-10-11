"""Independent mathematical invariants, hostile inputs, Unicode PDFs and API flow."""
import csv
import json
import math
import unittest
from decimal import Decimal, localcontext
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

import cvxpy as cp
import httpx
import numpy as np
from fastapi import FastAPI
from pypdf import PdfReader

from src.api.v1.interpolation import router, _capacity
from src.core.interpolation_limits import InterpolationBodyLimit
from src.services.interpolation import InputLimitError, MAX_UPLOAD_BYTES, Mode, calculate, monthly_csv, read_csv
from src.services.interpolation_pdf import build_pdf
from src.services.interpolation_smoothing import smooth_average, smooth_exit

EXAMPLE = Path(__file__).resolve().parents[2] / "frontend/public/examples/yearly-adoption-example.csv"


def annual_check(test, result):
    # Check the actual returned rows independently of the engine's diagnostics.
    with localcontext() as context:
        context.prec = 800
        for row in result["yearly"]:
            months = [item for item in result["monthly"] if item["year"] == row["year"]]
            test.assertEqual(len(months), 12)
            for column, target in enumerate(row["values"]):
                actual = sum((Decimal(str(item["values"][column])) for item in months), Decimal(0)) / 12 if result["mode"] == "average" else Decimal(str(months[-1]["values"][column]))
                tolerance = abs(Decimal(str(target))) * Decimal("1e-9") if target else Decimal("1e-12")
                test.assertLessEqual(abs(actual - Decimal(str(target))), tolerance)


class InputTests(unittest.TestCase):
    def test_excel_encodings_line_endings_and_percent_units(self):
        for codec in ("utf-8", "utf-8-sig", "utf-16", "utf-16-be", "cp1252", "gb18030"):
            name = "中文採用率" if codec not in ("cp1252",) else "Développement"
            for ending in ("\n", "\r\n", "\r"):
                source = f"Year,{name}{ending}2025,25%{ending}2026,40{ending}"
                content = source.encode(codec)
                if codec == "utf-16-be":
                    content = b"\xfe\xff" + content
                with self.subTest(codec=codec, ending=repr(ending)):
                    data = read_csv(content, "gb18030" if codec == "gb18030" else "auto")
                    self.assertEqual(data.columns, (name,))
                    self.assertEqual(data.values, ((25.,), (40.,)))
                    self.assertEqual(data.units, ("%",))

    def test_delimiters_relative_years_and_sorting_preserve_values(self):
        for delimiter in (",", ";", "\t"):
            source = f"sep={delimiter}\rYEAR{delimiter}Demand\rYear 2{delimiter}2500\rYear 1{delimiter}1000"
            data = read_csv(source.encode())
            self.assertTrue(data.sorted_input)
            self.assertEqual(data.years, (1, 2))
            self.assertEqual(data.values, ((1000.,), (2500.,)))

    def test_invalid_rows_headers_years_and_values_are_rejected(self):
        cases = [b"", b"year,V", b"year,V\n1,1\n3,3", b"year,V\n1,1\n1,2",
                 b"year,V\n1.5,2", b"year,V\n1e99999999,2", b"year,V\n9007199254740992,2",
                 b"year,V\n1,", b"year,V\n1,nan", b"year,V\n1,inf", b"year,V\n1,1e309",
                 b"year,V\n1,1e-400", b"year,V\n1,1e-323", b"year,V\n1,25%%", b"year,V\n1,=SUM(1)",
                 b"year,month\n1,2", b"year,V,v\n1,1,2", b"year,\n1,1",
                 b"year,=HYPERLINK()\n1,1", b"year,V\n1,1,2", b"year,V\n1,\"unfinished",
                 b"year,V\n1,1\x00"]
        for content in cases:
            with self.subTest(content=content[:40]), self.assertRaises(ValueError):
                read_csv(content)

    def test_resource_limits_precede_solver_allocation(self):
        cases = [b"x" * (MAX_UPLOAD_BYTES + 1),
                 ("year," + ",".join(f"v{i}" for i in range(21)) + "\n1," + ",".join("1" for _ in range(21))).encode(),
                 ("year,V\n" + "\n".join(f"{i},1" for i in range(101))).encode(),
                 ("year," + ",".join(f"v{i}" for i in range(20)) + "\n" + "\n".join(str(i) + "," + ",".join("1" for _ in range(20)) for i in range(51))).encode()]
        for content in cases:
            with self.subTest(size=len(content)), self.assertRaises(InputLimitError):
                read_csv(content)


class NumericalTests(unittest.TestCase):
    def test_full_requested_adoption_input_in_both_modes_without_mutation(self):
        content = EXAMPLE.read_bytes()
        data = read_csv(content)
        original = data.values
        self.assertEqual(data.values[9], (98., 98., 98.))
        self.assertTrue(all(row == (100., 100., 100.) for row in data.values[10:]))
        for mode in Mode:
            result = calculate(data, mode)
            self.assertEqual(len(result["monthly"]), 156)
            self.assertEqual(len(result["checks"]), 39)
            annual_check(self, result)
            self.assertEqual(data.values, original)
            self.assertEqual(EXAMPLE.read_bytes(), content)
            for series in result["series"]:
                self.assertGreaterEqual(series["first_month"], 0)
                if mode == Mode.average:
                    self.assertGreater(series["first_month"], 0)
                self.assertGreater(series["monthly_max"], 100)  # No hidden clipping.

    def test_average_absolute_numbers_negative_targets_and_zero(self):
        for values in ((1000, 2500, 4000), (-10, -5, 0), (0,), (1e-100, 2e-100), (1.79e308,)):
            with self.subTest(values=values):
                data = read_csv(("year,V\n" + "\n".join(f"{i + 1},{value}" for i, value in enumerate(values))).encode())
                result = calculate(data, Mode.average)
                self.assertGreater(result["monthly"][0]["values"][0], 0)
                annual_check(self, result)

    def test_exit_solves_first_year_globally_and_matches_linear_optimum(self):
        values = smooth_exit(np.array([[50.], [60.]]))[:, 0]
        expected = 50 + (np.arange(24) - 11) * 10 / 12
        np.testing.assert_allclose(values, expected, atol=1e-6, rtol=0)
        self.assertGreater(np.ptp(values[:12]), 0)
        anchored = smooth_exit(np.array([[1.], [4.]]))[:, 0]
        self.assertGreater(np.ptp(anchored[:12]), .1)
        self.assertEqual(anchored[11], 1.)
        self.assertEqual(anchored[23], 4.)
        self.assertGreaterEqual(anchored[0], 0)

    def test_single_exit_nonnegative_targets_flat_and_negative_target_rejected(self):
        for target in (0., 25., 2500., 1e-100, 1.79e308):
            np.testing.assert_array_equal(smooth_exit(np.array([[target]])), np.full((12, 1), target))
        with self.assertRaisesRegex(ValueError, "negative single-year"):
            smooth_exit(np.array([[-1.]]))

    def test_columns_are_independent_and_deterministic(self):
        targets = np.array(read_csv(EXAMPLE.read_bytes()).values)
        for function in (smooth_average, smooth_exit):
            combined = function(targets)
            np.testing.assert_array_equal(function(targets), combined)
            reordered = function(targets[:, ::-1])[:, ::-1]
            np.testing.assert_allclose(reordered, combined, rtol=1e-12, atol=1e-12)
            for index in range(3):
                np.testing.assert_allclose(function(targets[:, index:index + 1])[:, 0], combined[:, index], rtol=1e-12, atol=1e-12)

    def test_large_dynamic_range_underflow_and_overflow_are_rejected(self):
        for function in (smooth_average, smooth_exit):
            for targets in (np.array([[1.], [1e13]]), np.array([[math.inf]]), np.empty((0, 1))):
                with self.subTest(function=function.__name__, target=targets.tolist()), self.assertRaises(ValueError):
                    function(targets)
        with self.assertRaisesRegex(ValueError, "too small"):
            smooth_exit(np.array([[0.], [5e-324]]))
        with self.assertRaises(ValueError):
            smooth_average(np.array([[-1.79e308], [-1.79e308]]))

    def test_inaccurate_solver_status_and_corrupted_solver_output_are_not_released(self):
        def inaccurate(problem, **kwargs):
            problem._status = cp.OPTIMAL_INACCURATE
        with patch.object(cp.Problem, "solve", inaccurate), self.assertRaisesRegex(ValueError, "accuracy"):
            smooth_exit(np.array([[1.], [3.]]))
        with patch("src.services.interpolation_smoothing.smooth_average", return_value=np.full((24, 1), 1.)):
            with self.assertRaisesRegex(ValueError, "accuracy"):
                calculate(read_csv(b"year,V\n1,2\n2,3"), Mode.average)


class OutputTests(unittest.TestCase):
    def test_csv_and_json_keep_raw_numbers_and_original_names(self):
        result = calculate(read_csv("year,中文採用率\n1,1%\n2,4%".encode()), Mode.average)
        body = monthly_csv(result)
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(StringIO(body.decode("utf-8-sig"))))
        self.assertEqual(rows[0], ["year", "month", "中文採用率"])
        self.assertEqual([float(row[2]) for row in rows[1:]], [row["values"][0] for row in result["monthly"]])
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False))["monthly"], result["monthly"])

    def test_pdf_has_graph_input_monthly_numbers_and_embedded_unicode_fonts(self):
        result = calculate(read_csv("year,中文採用率,Δοκιμή,Рост\n1,1%,4%,8%\n2,4%,14%,25%".encode()), Mode.exit)
        body = build_pdf(result)
        reader = PdfReader(BytesIO(body))
        text = "\n".join(page.extract_text() for page in reader.pages)
        for value in (*result["columns"], "Yearly input", "Monthly output", "December targets"):
            self.assertIn(value, text)
        resources = [font.get_object() for page in reader.pages for font in page["/Resources"]["/Font"].values()]
        self.assertTrue(any("/ToUnicode" in font and "/FontFile2" in font["/FontDescriptor"].get_object() for font in resources if "/FontDescriptor" in font))
        self.assertTrue(any(b" l\n" in page.get_contents().get_data() for page in reader.pages))

    def test_pdf_unsupported_scripts_fail_clearly_csv_stays_available(self):
        result = calculate(read_csv("year,العربية\n1,5".encode()), Mode.exit)
        with self.assertRaisesRegex(ValueError, "right-to-left"):
            build_pdf(result)
        self.assertIn("العربية", monthly_csv(result).decode("utf-8-sig"))


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = FastAPI()
        app.add_middleware(InterpolationBodyLimit)
        app.include_router(router, prefix="/api/v1/interpolation")
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def post(self, action, content=b"year,V\n1,10\n2,20", **params):
        return await self.client.post("/api/v1/interpolation/" + action, params=params, files={"file": ("input.csv", content, "text/csv")})

    async def test_preview_calculate_export_all_formats_and_revision_guard(self):
        preview = await self.post("preview")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.headers["cache-control"], "no-store")
        self.assertNotIn("monthly", preview.json())
        response = await self.post("calculate", mode="average")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        annual_check(self, result)
        for format in ("csv", "json", "pdf"):
            download = await self.post("export", mode="average", format=format, calculation_id=result["calculation_id"])
            self.assertEqual(download.status_code, 200, download.text[:200] if format != "pdf" else "PDF failed")
            self.assertIn("attachment", download.headers["content-disposition"])
            self.assertEqual(download.headers["cache-control"], "no-store")
        stale = await self.post("export", mode="average", format="csv", calculation_id="0" * 64)
        self.assertEqual(stale.status_code, 409)

    async def test_errors_busy_service_and_upload_limits(self):
        bad = await self.post("calculate", b"year,V\n1,nan", mode="average")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.headers["cache-control"], "no-store")
        self.assertEqual((await self.post("calculate", mode="invalid")).status_code, 422)
        too_large = await self.post("preview", b"x" * (MAX_UPLOAD_BYTES + 1))
        self.assertEqual(too_large.status_code, 413)
        declared = await self.client.post("/api/v1/interpolation/preview", headers={"content-length": str(MAX_UPLOAD_BYTES * 2)}, content=b"tiny")
        self.assertEqual(declared.status_code, 413)
        _capacity.acquire()
        try:
            busy = await self.post("calculate", mode="exit")
            self.assertEqual(busy.status_code, 503)
            self.assertEqual(busy.headers["retry-after"], "3")
        finally:
            _capacity.release()

    async def test_chunked_multipart_body_is_bounded_without_content_length(self):
        async def body():
            yield b'--a\r\nContent-Disposition: form-data; name="file"; filename="input.csv"\r\n\r\n'
            yield b"x" * (MAX_UPLOAD_BYTES + 65537)
            yield b"\r\n--a--\r\n"
        response = await self.client.post("/api/v1/interpolation/preview", headers={"content-type": "multipart/form-data; boundary=a"}, content=body())
        self.assertEqual(response.status_code, 413)
