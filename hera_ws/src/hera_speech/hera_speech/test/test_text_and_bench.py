"""Testes de texto (normalização, alucinações, WER). Sem ROS/GPU."""
import unittest

from hera_ws.src.hera_speech.hera_speech.bench import wer
from hera_ws.src.hera_speech.hera_speech.transcriber import (apply_text_mode, device_chain, is_hallucination,
                                     normalize_for_match, parse_languages)


class TextTests(unittest.TestCase):
    def test_normalize_keeps_portuguese_letters(self):
        self.assertEqual(normalize_for_match('Não, avance!'), 'nao avance')

    def test_text_modes(self):
        self.assertEqual(apply_text_mode('Vá Para Cozinha.', 'raw'), 'Vá Para Cozinha.')
        self.assertEqual(apply_text_mode('Vá Para Cozinha.', 'lower'), 'vá para cozinha.')
        self.assertEqual(apply_text_mode('Vá Para Cozinha.', 'match'), 'va para cozinha')

    def test_hallucinations(self):
        self.assertTrue(is_hallucination('Obrigado por assistir!'))
        self.assertTrue(is_hallucination('Legendas pela comunidade Amara.org'))
        self.assertFalse(is_hallucination('obrigado, pode parar'))

    def test_languages(self):
        self.assertEqual(parse_languages('pt'), ['pt'])
        self.assertEqual(parse_languages('pt, EN'), ['pt', 'en'])
        self.assertEqual(parse_languages('auto'), [])

    def test_device_chain(self):
        self.assertEqual(device_chain('cpu', 'auto'), [('cpu', 'int8')])
        chain = device_chain('cuda', 'auto')
        self.assertEqual(chain[0], ('cuda', 'int8_float16'))
        self.assertEqual(chain[-1], ('cpu', 'int8'))      # último recurso

    def test_wer(self):
        self.assertEqual(wer('vá para a cozinha', 'va para a cozinha'), 0.0)
        self.assertAlmostEqual(wer('um dois tres quatro', 'um dois quatro'), 0.25)
        self.assertEqual(wer('oi', ''), 1.0)


if __name__ == '__main__':
    unittest.main()
