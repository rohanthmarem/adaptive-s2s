import json
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import numpy as np


class ResidualLayer(nn.Module):
    def __init__(self, original, layer_id, hooks):
        super().__init__()
        self.original = original
        self.layer_id = layer_id
        object.__setattr__(self, 'hooks', hooks)

    def __call__(self, xs, *args, **kwargs):
        result = self.original(xs, *args, **kwargs)
        return self.hooks.process(self.layer_id, result)


class ResidualHooks:
    def __init__(self, model, layers, start=0, stop=None, direction=None,
                 strength=0.0, donor=None, capture=False):
        self.model = model
        self.layers = sorted(set(layers))
        self.start, self.stop = start, stop
        self.strength, self.capture = strength, capture
        self.frame = -1
        self.records = {layer: [] for layer in self.layers}
        self.frames = {layer: [] for layer in self.layers}
        self.originals = {}
        width = model.cfg.transformer.d_model
        if not self.layers or any(i < 0 or i >= len(model.transformer.layers) for i in self.layers):
            raise ValueError('layers must be valid temporal transformer indices')
        if start < 0 or (stop is not None and stop <= start):
            raise ValueError('frame window must satisfy 0 <= start < stop')
        if not np.isfinite(strength):
            raise ValueError('strength must be finite')
        if direction is not None and donor is not None:
            raise ValueError('choose direction or donor, not both')
        self.direction = None
        self.donor = {}
        if direction is not None:
            value = np.load(direction, allow_pickle=False)
            if value.shape != (width,) or not np.isfinite(value).all():
                raise ValueError(f'direction must be a finite vector of shape ({width},)')
            self.direction = mx.array(value.astype(np.float32))
        if donor is not None:
            with np.load(donor, allow_pickle=False) as data:
                for layer in self.layers:
                    values = data[f'layer_{layer}']
                    frames = data[f'frames_{layer}']
                    if values.shape != (len(frames), width) or not np.isfinite(values).all():
                        raise ValueError('invalid donor activation shape or values')
                    if len(set(frames.tolist())) != len(frames):
                        raise ValueError('duplicate donor frames')
                    self.donor[layer] = dict(zip(frames.tolist(), values))

    def __enter__(self):
        for layer in self.layers:
            original = self.model.transformer.layers[layer]
            self.originals[layer] = original
            self.model.transformer.layers[layer] = ResidualLayer(original, layer, self)
        return self

    def __exit__(self, *_):
        for layer, original in self.originals.items():
            self.model.transformer.layers[layer] = original

    def process(self, layer, xs):
        if self.frame < self.start or (self.stop is not None and self.frame >= self.stop):
            return xs
        if xs.shape[:2] != (1, 1):
            raise ValueError('hooks require one streaming frame and batch size one')
        if self.capture:
            self.records[layer].append(np.array(xs.astype(mx.float32))[0, 0].copy())
            self.frames[layer].append(self.frame)
        if self.direction is not None and self.strength != 0:
            return xs + (self.strength * self.direction).astype(xs.dtype)[None, None, :]
        if self.donor:
            if self.frame not in self.donor[layer]:
                raise ValueError(f'donor missing layer {layer}, frame {self.frame}')
            return mx.array(self.donor[layer][self.frame]).astype(xs.dtype)[None, None, :]
        return xs

    def save(self, path, metadata):
        values = {}
        width = self.model.cfg.transformer.d_model
        for layer in self.layers:
            values[f'layer_{layer}'] = np.asarray(self.records[layer], dtype=np.float32).reshape(-1, width)
            values[f'frames_{layer}'] = np.asarray(self.frames[layer], dtype=np.int64)
        values['metadata'] = np.array(json.dumps({**metadata, 'capture_site': 'temporal_layer_output_before_intervention', 'layers': self.layers, 'start_frame': self.start, 'stop_frame': self.stop}))
        with Path(path).open('wb') as output:
            np.savez_compressed(output, **values)
