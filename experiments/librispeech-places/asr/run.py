import logging
import pickle
import torch
import torch.nn as nn

import platalea.asr as M
import platalea.dataset as D

torch.manual_seed(123)


batch_size = 8
<<<<<<< HEAD
hidden_size = 1024 * 3 // 4
=======
hidden_size = 1024
>>>>>>> Using np.memmap files for librispeech instead of pytorch
dropout = 0.0

logging.basicConfig(level=logging.INFO)

logging.info('Loading data')
data = dict(
    train=D.librispeech_loader(split='train', batch_size=batch_size,
<<<<<<< HEAD
                                shuffle=True, downsampling_factor=10),
=======
                               shuffle=True),
>>>>>>> Using np.memmap files for librispeech instead of pytorch
    val=D.librispeech_loader(split='val', batch_size=batch_size))
fd = D.LibriSpeechData
fd.init_vocabulary(data['train'].dataset)

# Saving config
pickle.dump(data['train'].dataset.get_config(),
            open('config.pkl', 'wb'))

config = dict(
    SpeechEncoder=dict(
        conv=dict(in_channels=39, out_channels=64, kernel_size=6, stride=2,
                  padding=0, bias=False),
<<<<<<< HEAD
        rnn=dict(input_size=64, hidden_size=hidden_size, num_layers=5,
=======
        rnn=dict(input_size=64, hidden_size=hidden_size, num_layers=6,
>>>>>>> Using np.memmap files for librispeech instead of pytorch
                 bidirectional=True, dropout=dropout),
        rnn_layer_type=nn.GRU),
    TextDecoder=dict(
        emb=dict(num_embeddings=fd.vocabulary_size(),
                 embedding_dim=hidden_size),
        drop=dict(p=dropout),
        att=dict(in_size_enc=hidden_size * 2, in_size_state=hidden_size,
                 hidden_size=hidden_size),
        rnn=dict(input_size=hidden_size * 3, hidden_size=hidden_size,
                 num_layers=1, dropout=dropout),
        out=dict(in_features=hidden_size * 3,
                 out_features=fd.vocabulary_size()),
        rnn_layer_type=nn.GRU,
        max_output_length=400,  # max length for flickr annotations is 199
        sos_id=fd.get_token_id(fd.sos),
        eos_id=fd.get_token_id(fd.eos),
        pad_id=fd.get_token_id(fd.pad)),
    inverse_transform_fn=fd.get_label_encoder().inverse_transform)

logging.info('Building model')
net = M.SpeechTranscriber(config)
run_config = dict(max_norm=2.0, max_lr=2 * 1e-4, epochs=32, opt='adam')

logging.info('Training')
M.experiment(net, data, run_config)
