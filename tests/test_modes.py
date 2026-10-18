"""입력 종류 분리와 공통 실행 옵션의 회귀 검사."""
import tempfile
import io
from contextlib import redirect_stderr
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluate_layers import evaluation_jobs, input_hashes
from train import run


class ModeTests(unittest.TestCase):
    def test_dispatch(self):
        with patch('train.main') as training, patch('evaluate_layers.main') as evaluation:
            run(['--mode', 'train', '--device', 'cpu'])
            training.assert_called_once_with(['--device', 'cpu'])
            run(['--mode', 'test', '--device', 'cpu'])
            evaluation.assert_called_once_with(['--split', 'test', '--device', 'cpu'])

    def test_validation_is_not_a_standalone_mode(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            run(['--mode', 'validation'])
        self.assertEqual(error.exception.code, 2)

    def test_test_split_rejects_train_validation_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def job(folder, target):
                path = root / folder
                path.mkdir(parents=True)
                (path / 'target.stl').write_bytes(target)
                (path / 'config.yaml').write_text('config')
                return path
            training = job('train/one', b'train')
            validation = job('validation/one', b'validation')
            test = job('test/one', b'new')
            settings = {'training_jobs': [{'input_sha256': input_hashes(training)}],
                        'validation_job': {'input_sha256': input_hashes(validation)}}
            def select():
                return evaluation_jobs(settings, 'test', root/'train', root/'validation', root/'test')
            self.assertEqual(len(select()), 1)
            for overlap in (b'train', b'validation'):
                (test/'target.stl').write_bytes(overlap)
                with self.assertRaisesRegex(ValueError, 'disjoint'):
                    select()
            (test/'target.stl').write_bytes(b'new')
            job('test/two', b'new')
            with self.assertRaisesRegex(ValueError, 'unique'):
                select()


if __name__ == '__main__':
    unittest.main()
