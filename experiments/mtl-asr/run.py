import logging
import random
import torch
import torch.nn as nn

import platalea.dataset as D
import platalea.mtl as M
from platalea.score import score, score_asr
from platalea.experiments.config import args

# Parsing arguments
args.enable_help()
args.parse()

# Setting general configuration
torch.manual_seed(args.seed)
random.seed(args.seed)
logging.basicConfig(level=logging.INFO)


batch_size = 8
hidden_size = 1024
dropout = 0.0

logging.info('Loading data')
data = dict(
    train=D.flickr8k_loader(args.meta, split='train', batch_size=batch_size, shuffle=True),
    val=D.flickr8k_loader(args.meta, split='val', batch_size=batch_size, shuffle=False))
fd = D.Flickr8KData

config = dict(
    SharedEncoder=dict(
        conv=dict(in_channels=39, out_channels=64, kernel_size=6, stride=2,
                  padding=0, bias=False),
        rnn=dict(input_size=64, hidden_size=hidden_size, num_layers=4,
                 bidirectional=True, dropout=dropout),
        rnn_layer_type=nn.GRU),
    SpeechEncoderTopSI=dict(
        rnn=dict(input_size=hidden_size * 2, hidden_size=hidden_size,
                 num_layers=1, bidirectional=True, dropout=dropout),
        att=dict(in_size=hidden_size * 2, hidden_size=128),
        rnn_layer_type=nn.GRU),
    SpeechEncoderTopASR=dict(
        rnn=dict(input_size=hidden_size * 2, hidden_size=hidden_size,
                 num_layers=1, bidirectional=True, dropout=dropout),
        rnn_layer_type=nn.GRU),
    ImageEncoder=dict(
        linear=dict(in_size=2048, out_size=hidden_size * 2),
        norm=True),
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
    inverse_transform_fn=fd.get_label_encoder().inverse_transform,
    margin_size=0.2,
    lmbd=0.5)

logging.info('Building model')
net = M.MTLNetASR(config)
run_config = dict(max_norm=2.0, max_lr=2 * 1e-4, epochs=32)

tasks = [dict(name='SI', net=net.SpeechImage, data=data, eval=score),
         dict(name='ASR', net=net.SpeechTranscriber, data=data, eval=score_asr)]

logging.info('Training')
M.experiment(net, tasks, run_config)
