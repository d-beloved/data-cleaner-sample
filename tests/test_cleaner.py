import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from cleaner import CleanConfig, clean, read_table, write_table
from cleaner import text as T


class TextTests(unittest.TestCase):
    def test_html_urls_emoji_handles(self):
        raw = "LOVE <b>it</b>&amp;more 😍 https://x.co/a @bob #win   sooooo good"
        self.assertEqual(T.clean_text(raw), "love it&more win soo good")

    def test_block_tags_keep_words_apart(self):
        self.assertEqual(T.clean_text("<p>Five stars.</p><p>Still <i>new</i>.</p>"), "five stars. still new.")

    def test_comparison_signs_are_not_tags(self):
        self.assertEqual(T.clean_text("price < 50 and rating > 3"), "price < 50 and rating > 3")

    def test_pii_masking(self):
        out = T.clean_text("Mail a.b@x.com or call +1 (555) 010-2030", mask_pii=True)
        self.assertEqual(out, "mail [email] or call [phone]")

    def test_pii_left_alone_by_default(self):
        self.assertIn("a.b@x.com", T.clean_text("mail a.b@x.com"))

    def test_curly_quotes_and_unicode(self):
        self.assertEqual(T.clean_text("It’s Ｆine — ok"), "it's fine - ok")

    def test_dedupe_key(self):
        self.assertEqual(T.dedupe_key("  Great, PRODUCT!! "), T.dedupe_key("great product"))

    def test_tokenize(self):
        self.assertEqual(T.tokenize("The cat isn't here", remove_stopwords=True), ["cat", "isn't"])


class PipelineTests(unittest.TestCase):
    def test_column_names(self):
        df, rep = clean(pd.DataFrame({" First Name ": ["a"], "E-mail": ["b"], "first name": ["c"]}))
        self.assertEqual(list(df.columns), ["first_name", "e_mail", "first_name_2"])

    def test_null_tokens_and_empty_rows_columns(self):
        df, rep = clean(pd.DataFrame({"a": ["x", "N/A", ""], "b": ["y", "null", " "], "c": ["", "", ""]}))
        self.assertEqual(list(df.columns), ["a", "b"])
        self.assertEqual(len(df), 1)
        self.assertEqual(rep["columns_dropped"], ["c"])

    def test_numeric_inference(self):
        df, rep = clean(pd.DataFrame({"price": ["$1,200", " 35 ", "7"] * 4, "zip": ["01234", "90210", "10001"] * 4,
                                      "n": list(range(12))}))
        self.assertEqual(df["price"].tolist()[:3], [1200, 35, 7])
        self.assertEqual(df["zip"].tolist()[0], "01234")  # leading zeros survive

    def test_invalid_numbers_reported(self):
        df, rep = clean(pd.DataFrame({"r": ["1", "2", "x"], "k": ["a", "b", "c"]}), {"numeric_columns": ["r"]})
        self.assertEqual(rep["numeric_columns"]["r"]["invalid_examples"], ["x"])
        self.assertTrue(pd.isna(df["r"][2]))

    def test_dates(self):
        df, rep = clean(pd.DataFrame({"d": ["2026-03-14", "March 5, 2026", "2026-02-30", "03/04/2026"], "k": list("abcd")}),
                        {"date_columns": ["d"]})
        self.assertEqual(df["d"].tolist()[:2], ["2026-03-14", "2026-03-05"])
        self.assertTrue(pd.isna(df["d"][2]))
        self.assertEqual(df["d"][3], "2026-03-04")
        self.assertEqual(rep["date_columns"]["d"]["unparseable_set_to_missing"], 1)

    def test_auto_detects_dates_and_text(self):
        data = {"created_at": ["2026-01-05", "Jan 7, 2026", "bad"] * 2, "amount_on_hand": ["1", "2", "3"] * 2,
                "feedback": ["The same long sentence about a product, repeated."] * 3 + ["Another long sentence about delivery."] * 3}
        df, rep = clean(pd.DataFrame(data), {"drop_duplicates": False})
        self.assertEqual(rep["text_columns"], ["feedback"])
        self.assertEqual(list(rep["date_columns"]), ["created_at"])
        self.assertEqual(df["created_at"][1], "2026-01-07")

    def test_dayfirst(self):
        df, _ = clean(pd.DataFrame({"d": ["03/04/2026"], "k": ["a"]}), {"date_columns": ["d"], "dayfirst": True})
        self.assertEqual(df["d"][0], "2026-04-03")

    def test_categories(self):
        data = {"country": ["USA", "usa", "U.S.A.", "UK", "uk ", "UK"] * 3, "n": list(range(18))}
        df, rep = clean(pd.DataFrame(data), {"category_maps": {"country": {"U.S.A.": "USA"}}})
        self.assertEqual(sorted(df["country"].unique()), ["UK", "USA"])

    def test_duplicates_ignore_ids_case_punctuation(self):
        data = {"id": [1, 2, 3], "text": ["Great product, would buy again and again!", "great product would buy again and again", "Something else entirely, not the same at all."]}
        df, rep = clean(pd.DataFrame(data))
        self.assertEqual(rep["duplicates_removed"], 1)
        self.assertEqual(df["id"].tolist(), [1, 3])

    def test_required_and_fill(self):
        data = {"name": ["a", None, "c", "d"], "score": [1, 2, None, 6], "k": list("wxyz")}
        df, rep = clean(pd.DataFrame(data), {"required_columns": ["name"], "numeric_fill": "median"})
        self.assertEqual(len(df), 3)
        self.assertEqual(df["score"].tolist(), [1, 3.5, 6])
        self.assertEqual(rep["rows_dropped"]["missing_required"], 1)

    def test_nothing_filled_by_default(self):
        df, rep = clean(pd.DataFrame({"score": [1, None, 3], "k": list("abc")}))
        self.assertEqual(rep["values_filled"], {})
        self.assertEqual(int(df["score"].isna().sum()), 1)

    def test_unknown_config_key_rejected(self):
        with self.assertRaises(ValueError):
            CleanConfig.from_dict({"typo": 1})

    def test_missing_config_column_warns(self):
        _, rep = clean(pd.DataFrame({"a": ["x"]}), {"date_columns": ["nope"]})
        self.assertIn("nope", rep["warnings"][0])

    def test_empty_frame(self):
        df, rep = clean(pd.DataFrame({"a": []}))
        self.assertEqual(rep["rows_out"], 0)

    def test_input_not_mutated(self):
        src = pd.DataFrame({"A": [" x "]})
        clean(src)
        self.assertEqual(src["A"][0], " x ")


class IoTests(unittest.TestCase):
    def test_round_trip_formats(self):
        df = pd.DataFrame({"a": ["x", "y"], "b": [1, 2]})
        with tempfile.TemporaryDirectory() as tmp:
            for ext in (".csv", ".tsv", ".xlsx", ".json", ".jsonl"):
                path = Path(tmp) / f"t{ext}"
                write_table(df, path)
                back, _ = clean(read_table(path))
                self.assertEqual(back["a"].tolist(), ["x", "y"], ext)
                self.assertEqual([int(v) for v in back["b"]], [1, 2], ext)

    def test_semicolon_csv_and_bom_and_cp1252(self):
        self.assertEqual(list(read_table("﻿a;b\n1;2\n".encode("utf-8"), name="x.csv").columns), ["a", "b"])
        self.assertEqual(read_table("a,b\ncaf\xe9,2\n".encode("cp1252"), name="x.csv")["a"][0], "café")

    def test_wrapped_and_nested_json(self):
        raw = json.dumps({"data": [{"a": 1, "u": {"name": "x"}, "tags": ["p", "q"]}]}).encode()
        df, _ = clean(read_table(raw, name="x.json"))
        self.assertEqual(df["u_name"][0], "x")
        self.assertEqual(df["tags"][0], '["p", "q"]')

    def test_bad_inputs(self):
        for raw, name in ((b"", "x.csv"), (b"a", "x.pdf"), (b"[1,2]", "x.json")):
            with self.assertRaises(ValueError):
                read_table(raw, name=name)


if __name__ == "__main__":
    unittest.main()
