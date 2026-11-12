import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from core import sources, webcontent
from core.wiki_noise import clean_wiki_ui_line, is_wiki_ui_noise


REJECT = (
    "modifier - modifier le code - modifier Wikidata",
    "modifier le code",
    "[modifier | modifier le code]",
    "Portail de l'Égypte antique",
    "Notes et références",
    "Catégorie : Pyramide d'Égypte",
)
KEEP = (
    "La pyramide de Khéops, ou grande pyramide de Gizeh, est un monument construit par les Égyptiens de l'Antiquité.",
    "Il faut modifier le plan pour tenir les délais.",
    "Construction de la pyramide de kheops : l'histoire derrière le sujet",
    "Tombeau présumé du souverain Khéops, elle fut édifiée il y a plus de 4 500 ans.",
    "Le code de Hammurabi est un ensemble de lois babyloniennes.",
)


class WikiNoiseTests(unittest.TestCase):
    def test_supplied_six_rejections_and_five_keeps(self):
        for line in REJECT:
            with self.subTest(reject=line):
                self.assertTrue(is_wiki_ui_noise(line))
        for line in KEEP:
            with self.subTest(keep=line):
                self.assertFalse(is_wiki_ui_noise(line))

    def test_sentence_cleaner_removes_toolbar_and_preserves_prose(self):
        text = REJECT[0] + "\n" + KEEP[0] + " " + KEEP[1]
        result = sources._clean_sentences(text)
        self.assertEqual(result, [KEEP[0], KEEP[1]])

    def test_joined_toolbar_prefix_preserves_article_sentence(self):
        self.assertEqual(clean_wiki_ui_line(REJECT[0] + " " + KEEP[0]), KEEP[0])

    def test_wikipedia_paragraph_parser_rejects_toolbar(self):
        parser = webcontent._WikiParagraphs()
        parser.feed("<p>" + REJECT[0] + "</p><p>" + KEEP[0] + "</p>")
        self.assertEqual(parser.paragraphs, [KEEP[0]])

    def test_wikipedia_parser_skips_edit_section_markup(self):
        parser = webcontent._WikiParagraphs()
        parser.feed('<p><span class="mw-editsection">modifier le code</span>' + KEEP[0] + "</p>")
        self.assertEqual(parser.paragraphs, [KEEP[0]])

    def test_old_cached_article_is_cleaned_without_rewriting_cache(self):
        cached = json.dumps({"title": "Pyramide de Khéops", "text": REJECT[0] + " " + KEEP[0]})
        with patch.object(webcontent, "_cache_get", return_value=[cached]), \
                patch.object(webcontent, "_cache_put") as write, \
                patch.object(webcontent, "_get") as network:
            article = webcontent._wiki_full_article("fr", "Pyramide de Khéops")
        self.assertEqual(article["text"], KEEP[0])
        network.assert_not_called()
        write.assert_not_called()

    def test_old_local_topic_snapshot_is_cleaned_before_scene_splitting(self):
        topic = "construction de la pyramide de kheops"
        article = {"title": "Pyramide de Khéops", "text": REJECT[0] + " " + KEEP[0]
                   + " " + KEEP[3] + " " + KEEP[0], "url": ""}
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "wiki_cache.json"
            cache_path.write_text(json.dumps({f"local:fr:{topic}": {
                "titles": [json.dumps(article, ensure_ascii=False)]}}, ensure_ascii=False),
                encoding="utf-8")
            before = cache_path.read_bytes()
            with patch.object(webcontent, "_cache_path", return_value=str(cache_path)), \
                    patch.object(webcontent.content_mod, "with_visual_plans",
                                 side_effect=lambda script: script), \
                    patch.object(webcontent, "_get") as network:
                script = webcontent.local_topic_script(topic, "fr", 35, "sujet")
            self.assertIsNotNone(script)
            self.assertTrue(any("La pyramide de Khéops" in scene for scene in script["scenes"]))
            self.assertFalse(any("modifier le code" in scene for scene in script["scenes"]))
            self.assertNotIn("modifier le code", script["caption"])
            self.assertEqual(cache_path.read_bytes(), before)
            network.assert_not_called()

    def test_title_and_caption_omit_toolbar_and_duplicate_hook(self):
        hook = KEEP[2]
        title = webcontent._clean_title(REJECT[0] + " " + hook)
        self.assertNotIn("modifier", title.casefold())
        caption, _ = webcontent._caption(hook, hook, [hook, REJECT[0], hook, KEEP[0]],
                                         "histoire", "fr", [], "")
        self.assertNotIn("modifier", caption.casefold())
        self.assertEqual(caption.count(hook), 1)
        self.assertIn(KEEP[0], caption)


if __name__ == "__main__":
    unittest.main()
