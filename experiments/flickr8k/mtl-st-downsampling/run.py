<<<<<<< HEAD
import configargparse
import logging
import pickle
import random
from shutil import copyfile
import torch
=======
import logging
import pickle
from shutil import copyfile
import torch
import torch.nn as nn
>>>>>>> Using np.memmap files for librispeech instead of pytorch

import platalea.dataset as D
import platalea.mtl as M
from platalea.score import score, score_speech_text
from utils.copy_best import copy_best

<<<<<<< HEAD
# Parsing arguments
parser = configargparse.get_argument_parser('platalea')
parser.add_argument(
    '--seed', default=123, type=int,
    help='seed for sources of randomness (default: 123)')
config_args, _ = parser.parse_known_args()

# Setting general configuration
torch.manual_seed(config_args.seed)
random.seed(config_args.seed)
logging.basicConfig(level=logging.INFO)

=======
torch.manual_seed(123)
>>>>>>> Using np.memmap files for librispeech instead of pytorch

batch_size = 8
hidden_size = 1024
dropout = 0.0
<<<<<<< HEAD
=======
feature_fname = 'mfcc_delta_features.pt'

logging.basicConfig(level=logging.INFO)
>>>>>>> Using np.memmap files for librispeech instead of pytorch

factors = [3, 9, 27, 81, 243]
lz = len(str(abs(factors[-1])))
for ds_factor in factors:
    logging.info('Loading data')
    data = dict(
        train=D.flickr8k_loader(split='train', batch_size=batch_size,
<<<<<<< HEAD
                                shuffle=True, downsampling_factor=ds_factor),
        val=D.flickr8k_loader(split='val', batch_size=batch_size,
                              shuffle=False))
    fd = D.Flickr8KData
=======
                                shuffle=True, feature_fname=feature_fname,
                                downsampling_factor=ds_factor),
        val=D.flickr8k_loader(split='val', batch_size=batch_size,
                              shuffle=False, feature_fname=feature_fname))
    fd = D.Flickr8KData
    fd.init_vocabulary(data['train'].dataset)

    # Saving config
    pickle.dump(dict(feature_fname=feature_fname,
                     label_encoder=fd.get_label_encoder(),
                     language='en'),
                open('config.pkl', 'wb'))
>>>>>>> Using np.memmap files for librispeech instead of pytorch

    config = dict(
        SharedEncoder=dict(
            conv=dict(in_channels=39, out_channels=64, kernel_size=6, stride=2,
                      padding=0, bias=False),
            rnn=dict(input_size=64, hidden_size=hidden_size, num_layers=2,
                     bidirectional=True, dropout=dropout),
            rnn_layer_type=nn.GRU),
        SpeechEncoderTopSI=dict(
            rnn=dict(input_size=hidden_size * 2, hidden_size=hidden_size,
                     num_layers=2, bidirectional=True, dropout=dropout),
            att=dict(in_size=hidden_size * 2, hidden_size=128),
            rnn_layer_type=nn.GRU),
        SpeechEncoderTopST=dict(
            att=dict(in_size=hidden_size * 2, hidden_size=128)),
        ImageEncoder=dict(
            linear=dict(in_size=hidden_size * 2, out_size=hidden_size * 2),
            norm=True),
        TextEncoder=dict(
            emb=dict(num_embeddings=D.Flickr8KData.vocabulary_size(),
                     embedding_dim=128),
            rnn=dict(input_size=128, hidden_size=1024, num_layers=1,
                     bidirectional=True, dropout=0),
            att=dict(in_size=1024 * 2, hidden_size=128)),
        margin_size=0.2,
        lmbd=0.5)

    logging.info('Building model')
    net = M.MTLNetSpeechText(config)
<<<<<<< HEAD
    run_config = dict(max_norm=2.0, max_lr=2 * 1e-4, epochs=32)
=======
    run_config = dict(max_norm=2.0, max_lr=2 * 1e-4, epochs=32, opt='adam')
>>>>>>> Using np.memmap files for librispeech instead of pytorch

    tasks = [
        dict(name='SI', net=net.SpeechImage, data=data, eval=score),
        dict(name='ST', net=net.SpeechText, data=data, eval=score_speech_text)]

    logging.info('Training')
    M.experiment(net, tasks, run_config)
    suffix = str(ds_factor).zfill(lz)
    res_fname = 'result_{}.json'.format(suffix)
    copyfile('result.json', res_fname)
    copy_best(res_fname, 'net_{}.best.pt'.format(ds_factor),
              experiment_type='mtl')