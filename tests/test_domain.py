"""domain 계층 단위 시험 (모델·네트워크 없이 바로 돎).

실행: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storybook.domain import choices, story_format, textnorm, voices  # noqa: E402


class TextNormTest(unittest.TestCase):
    def test_native_counters(self):
        self.assertEqual(textnorm.to_speech("문어는 3살이었어요."), "문어는 세 살이었어요.")
        self.assertEqual(textnorm.to_speech("사과 12개와 물고기 20마리"), "사과 열두 개와 물고기 스무 마리")
        self.assertEqual(textnorm.to_speech("1번째 친구, 2번째 친구"), "첫 번째 친구, 두 번째 친구")
        self.assertEqual(textnorm.to_speech("오후 3시에 2시간 동안"), "오후 세 시에 두 시간 동안")

    def test_sino_numbers(self):
        self.assertEqual(textnorm.to_speech("2025년 3월 5일"), "이천이십오년 삼월 오일")
        self.assertEqual(textnorm.to_speech("100명이 모였어요"), "백 명이 모였어요")
        self.assertEqual(textnorm.to_speech("1,000원"), "천원")
        self.assertEqual(textnorm.to_speech("50% 할인"), "오십 퍼센트 할인")


class StoryFormatTest(unittest.TestCase):
    def test_valid_json_line(self):
        ev = story_format.parse_line('{"type": "line", "who": "해설", "text": "안녕", "emotion": "다정하게"}')
        self.assertEqual(ev["type"], "line")
        self.assertEqual(ev["text"], "안녕")

    def test_broken_json_line_is_recovered(self):
        # 작은 모델이 } 대신 ] 로 닫는 경우
        ev = story_format.parse_line('{"type": "page", "no": 3, "scene": "x", "cast": ["a", "b"]]')
        self.assertEqual((ev["type"], ev["no"], ev["cast"]), ("page", 3, ["a", "b"]))

    def test_not_an_event(self):
        self.assertIsNone(story_format.parse_line("그냥 문장"))
        self.assertIsNone(story_format.parse_line('{"text": "type 이 없음"}'))

    def test_foreign_detection(self):
        self.assertTrue(story_format.has_foreign("외로운孤单 문어"))
        self.assertTrue(story_format.has_foreign("따뜻한tentacles의 모험"))
        self.assertFalse(story_format.has_foreign("평범한 한국어 문장"))
        self.assertFalse(story_format.has_foreign("OK 좋아"))  # 2글자 영어는 허용

    def test_cut_raw(self):
        raw = ('{"type": "title", "text": "t"}\n{"type": "line", "who": "해설", "text": "a"}\n'
               '{"type": "chapter", "no": 2, "title": "x"}\n{"type": "page", "no": 3, "sce')
        self.assertTrue(story_format.cut_before_next_chapter(raw).endswith('"text": "a"}\n'))
        raw2 = '{"type": "line", "text": "a"}\n{"type": "choice", "question": "q"}\n{"type": "page"'
        self.assertTrue(story_format.cut_after_choice(raw2).endswith('"question": "q"}\n'))


class ChoicesTest(unittest.TestCase):
    OPTS = ["반짝이는 동굴", "해초 숲"]

    def test_match_by_words(self):
        self.assertEqual(choices.match_choice("반짝이는 동굴로 갈래", self.OPTS), 0)
        self.assertEqual(choices.match_choice("숲으로 가자", self.OPTS), 1)
        self.assertEqual(choices.match_choice("숲!", self.OPTS), 1)

    def test_match_by_ordinal(self):
        self.assertEqual(choices.match_choice("두 번째", self.OPTS), 1)
        self.assertEqual(choices.match_choice("첫 번째 거", self.OPTS), 0)

    def test_unknown(self):
        self.assertIsNone(choices.match_choice("음", self.OPTS))

    def test_question_text(self):
        self.assertEqual(choices.question_text("어디로 갈까요?", self.OPTS),
                         "어디로 갈까요? 첫 번째, 반짝이는 동굴. 두 번째, 해초 숲.")


class VoicesTest(unittest.TestCase):
    GIRL_ALTS = ["Sohee", "Ono_Anna", "Vivian", "Serena"]

    def test_girl_never_gets_male_voice_when_narrator_conflicts(self):
        got = voices.pick_speaker("girl", "Sohee", self.GIRL_ALTS, narrator="Sohee", taken=set())
        self.assertEqual(got, "Ono_Anna")

    def test_distinct_from_other_characters(self):
        got = voices.pick_speaker("girl", "Sohee", self.GIRL_ALTS, narrator="Aiden", taken={"Sohee"})
        self.assertEqual(got, "Ono_Anna")

    def test_same_as_narrator_mode(self):
        self.assertEqual(voices.pick_speaker("girl", "Sohee", self.GIRL_ALTS, "Ryan", set(), same_as_narrator=True), "Ryan")

    def test_instruct(self):
        self.assertEqual(voices.narrator_instruct("", "천천히 읽어 주세요.", "다정하게"),
                         "천천히 읽어 주세요. 이번 문장은 다정하게 말하세요.")
        self.assertEqual(voices.emotion_instruct("맑은 목소리로", ""), "맑은 목소리로")


if __name__ == "__main__":
    unittest.main()
