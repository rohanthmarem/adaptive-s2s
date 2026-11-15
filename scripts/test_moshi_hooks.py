import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import mlx.core as mx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'docs/duplex'))
from moshi_hooks import ResidualHooks


class HookTests(unittest.TestCase):
    def model(self):
        return SimpleNamespace(cfg=SimpleNamespace(transformer=SimpleNamespace(d_model=4)),
                               transformer=SimpleNamespace(layers=[lambda x: x]))

    def test_window_capture_and_restore(self):
        model = self.model()
        original = model.transformer.layers[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'v.npy'
            np.save(path, np.ones(4))
            hooks = ResidualHooks(model, [0], start=1, stop=2, direction=path, strength=2, capture=True)
            with self.assertRaisesRegex(RuntimeError, 'test'):
                with hooks:
                    for frame, expected in [(0, 0), (1, 2), (2, 0)]:
                        hooks.frame = frame
                        result = model.transformer.layers[0](mx.zeros((1, 1, 4)))
                        np.testing.assert_array_equal(np.array(result), np.full((1, 1, 4), expected))
                    raise RuntimeError('test')
            self.assertIs(model.transformer.layers[0], original)
            self.assertEqual(hooks.frames[0], [1])
            np.testing.assert_array_equal(hooks.records[0][0], np.zeros(4))

    def test_invalid_configuration(self):
        for kwargs in [dict(layers=[-1]), dict(layers=[1]), dict(layers=[0], start=-1),
                       dict(layers=[0], stop=0), dict(layers=[0], strength=float('nan'))]:
            with self.assertRaises(ValueError):
                ResidualHooks(self.model(), **kwargs)

    def test_donor_missing_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'donor.npz'
            np.savez(path, layer_0=np.ones((1, 4)), frames_0=np.array([1]))
            hooks = ResidualHooks(self.model(), [0], donor=path)
            hooks.frame = 0
            with self.assertRaisesRegex(ValueError, 'missing'):
                hooks.process(0, mx.zeros((1, 1, 4)))


if __name__ == '__main__':
    unittest.main()
