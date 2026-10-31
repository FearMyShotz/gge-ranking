import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import update_gacha


class GachaTests(unittest.TestCase):
    def setUp(self):
        self.sources = {
            "highscore": "\n".join(f"__s0local42.{key}_GACHA_EVENT = {value};" for key, value in [("DECO", 80), ("CHRISTMAS", 81), ("EASTER", 82), ("SUMMER", 83), ("ANNIVERSARY", 85), ("HALLOWEEN", 86), ("BLACK_FRIDAY", 87), ("CARNIVAL", 88)]),
            "event": "\n".join(f"__s0local30.EVENTTYPE_{key}_GACHA = {value};" for key, value in [("DECO", 126), ("CHRISTMAS", 127), ("EASTER", 128), ("SUMMER", 130), ("ANNIVERSARY", 131), ("HALLOWEEN", 132), ("BLACK_FRIDAY", 134), ("CARNIVAL", 135)]),
        }

    def test_matches_client_enums(self):
        mapping = update_gacha.parse_client(self.sources)
        self.assertEqual(len(mapping), 8)
        self.assertEqual(next(item for item in mapping if item["type"] == "HALLOWEEN_GACHA"), {"type": "HALLOWEEN_GACHA", "eventId": 132, "rankingId": 86, "key": "event_title_132"})

    def test_minified_official_bundle(self):
        sources = {
            "highscore": self.sources["highscore"].replace("__s0local42", "q").replace(";\n", ",").replace(";", ","),
            "event": self.sources["event"].replace("__s0local30", "P").replace(";\n", ",").replace(";", ","),
        }
        self.assertEqual(update_gacha.parse_client(sources), update_gacha.parse_client(self.sources))

    def test_mismatched_enums_rejected(self):
        self.sources["event"] = self.sources["event"].replace("__s0local30.EVENTTYPE_HALLOWEEN_GACHA = 132;", "")
        with self.assertRaises(ValueError):
            update_gacha.parse_client(self.sources)

    def test_live_seasonal_overrides_deco(self):
        mapping = update_gacha.parse_client(self.sources)
        self.assertEqual(update_gacha.choose(mapping, {80, 86})["rankingId"], 86)
        self.assertEqual(update_gacha.choose(mapping, {80})["rankingId"], 80)

    def test_ambiguous_or_missing_is_rejected(self):
        mapping = update_gacha.parse_client(self.sources)
        with self.assertRaises(ValueError):
            update_gacha.choose(mapping, {80, 85, 86})
        with self.assertRaises(ValueError):
            update_gacha.choose(mapping, set())

    def test_existing_non_gacha_events_preserved(self):
        data = {"player": {"honorPoints": {"id": 5}, "event_title_130": {"id": 83}}, "alliance": {"allianceHonor": {"id": 10}}}
        result = update_gacha.merge_events(data, update_gacha.parse_client(self.sources))
        self.assertEqual(result["alliance"], data["alliance"])
        self.assertEqual(result["player"]["honorPoints"], data["player"]["honorPoints"])
        self.assertEqual(result["player"]["event_title_132"]["id"], 86)


if __name__ == "__main__":
    unittest.main()
