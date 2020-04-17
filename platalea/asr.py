from collections import Counter
import json
import logging
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

from platalea.basic import cyclic_scheduler
import platalea.dataset as D
from platalea.decoders import TextDecoder
from platalea.encoders import SpeechEncoder
import platalea.loss
import platalea.score
import platalea.config

_device = platalea.config.device()


class SpeechTranscriber(nn.Module):
    def __init__(self, config):
        super(SpeechTranscriber, self).__init__()
        self.config = config
        # Components can be pre-instantiated or configured through a dictionary
        if isinstance(config['SpeechEncoder'], nn.Module):
            self.SpeechEncoder = config['SpeechEncoder']
        else:
            self.SpeechEncoder = SpeechEncoder(config['SpeechEncoder'])
        if isinstance(config['TextDecoder'], nn.Module):
            self.TextDecoder = config['TextDecoder']
        else:
            self.TextDecoder = TextDecoder(config['TextDecoder'])
        self.inverse_transform_fn = config['inverse_transform_fn']

    def forward(self, speech, seq_len, target=None):
        out = self.SpeechEncoder(speech, seq_len)
        pred, attn_weights = self.TextDecoder.decode(out, target)
        return pred, attn_weights

    def transcribe(self, audio, beam_size=None):
        audio = torch.utils.data.DataLoader(dataset=audio, batch_size=32,
                                            shuffle=False,
                                            collate_fn=D.batch_audio)
        trn = []
        for a, l in audio:
            if beam_size is None:
                preds, _ = self.forward(a.to(_device), l.to(_device))
                preds = preds.argmax(dim=2).detach().cpu().numpy().astype(int)
            else:
                enc_out = self.SpeechEncoder(a.to(_device), l.to(_device))
                preds = self.TextDecoder.beam_search(enc_out, beam_size)
            trn.append(self.pred2trn(preds))
        trn = np.concatenate(trn)
        return trn

    def pred2trn(self, preds):
        trn = []
        for p in preds:
            i_eos = (p == self.TextDecoder.eos_id).nonzero()[0]
            i_last = i_eos[0] if i_eos.shape[0] > 0 else p.shape[0]
            chars = self.inverse_transform_fn(p[:i_last])
            trn.append(''.join(chars))
        return trn

    def cost(self, item):
        target = item['text'][:, 1:].contiguous()
        pred, _ = self.forward(item['audio'], item['audio_len'], target)

        # Masking padding
        # - flatten vectors
        target = target.view(-1)
        pred = pred.view(-1, self.TextDecoder.num_tokens)
        # - compute and apply mask
        mask = (target != self.TextDecoder.pad_id)
        target = target[mask]
        pred = pred[mask, :]

        cost = F.cross_entropy(pred, target)
        return cost


def experiment(net, data, config, slt=False):
    def val_loss():
        with torch.no_grad():
            net.eval()
            result = []
            for item in data['val']:
                item = {key: value.to(_device) for key, value in item.items()}
                result.append(net.cost(item).item())
            net.train()
        return torch.tensor(result).mean()

    net.to(_device)
    net.train()
    if 'lr' in config.keys():
        lr = config['lr']
    else:
        lr = 1.0
    if 'opt' in config.keys() and config['opt'] == 'adam':
        optimizer = optim.Adam(net.parameters(), lr=lr)
        scheduler = cyclic_scheduler(optimizer, len(data['train']),
                                     max_lr=config['max_lr'], min_lr=1e-6)
    else:
        optimizer = optim.Adadelta(net.parameters(), lr=lr, rho=0.95, eps=1e-8)
    optimizer.zero_grad()

    with open("result.json", "w") as out:
        best_score = -np.inf
        for epoch in range(1, config['epochs']+1):
            cost = Counter()
            for j, item in enumerate(data['train'], start=1):
                item = {key: value.to(_device) for key, value in item.items()}
                loss = net.cost(item)
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), config['max_norm'])
                optimizer.step()
                if 'opt' in config.keys() and config['opt'] == 'adam':
                    scheduler.step()
                cost += Counter({'cost': loss.item(), 'N': 1})
                if j % 100 == 0:
                    logging.info("train {} {} {}".format(
                        epoch, j, cost['cost'] / cost['N']))
                if j % 400 == 0:
                    logging.info("valid {} {} {}".format(epoch, j, val_loss()))
            with torch.no_grad():
                net.eval()
                if slt:
                    result = platalea.score.score_slt(net, data['val'].dataset)
                else:
                    result = platalea.score.score_asr(net, data['val'].dataset)
                net.train()
            result['epoch'] = epoch
            json.dump(result, out)
            print('', file=out, flush=True)
            if 'epsilon_decay' in config.keys():
                if slt:
                    score = result['bleu']
                else:
                    score = -result['wer']['WER']
                if score > best_score:
                    best_score = score
                else:
                    net.load_state_dict(torch.load('net.{}.pt'.format(epoch - 1)))
                    for p in optimizer.param_groups:
                        p["eps"] *= config['epsilon_decay']
                        print('Epsilon decay - new value: ', p["eps"])
                logging.info("Saving model in net.{}.pt".format(epoch))
                # Saving weights only
                torch.save(net.state_dict(), "net.{}.pt".format(epoch))
            else:
                logging.info("Saving model in net.{}.pt".format(epoch))
                torch.save(net, "net.{}.pt".format(epoch))
    if 'epsilon_decay' in config.keys():
        # Save full model for inference
        torch.save(net, 'net.best.pt')


def get_default_config():
    fd = D.Flickr8KData
    return dict(
        SpeechEncoder=dict(
            conv=dict(in_channels=39, out_channels=64, kernel_size=6, stride=2,
                      padding=0, bias=False),
            rnn=dict(input_size=64, hidden_size=1024, num_layers=4,
                     bidirectional=True, dropout=0.0),
            rnn_layer_type=nn.GRU),
        TextDecoder=dict(
            emb=dict(num_embeddings=fd.vocabulary_size(),
                     embedding_dim=1024),
            drop=dict(p=0.0),
            att=dict(in_size_enc=1024 * 2, in_size_state=1024,
                     hidden_size=1024),
            rnn=dict(input_size=1024 * 3, hidden_size=1024,
                     num_layers=1, dropout=0.0),
            out=dict(in_features=1024 * 3,
                     out_features=fd.vocabulary_size()),
            rnn_layer_type=nn.GRU,
            max_output_length=400,  # max length for flickr annotations is 199
            sos_id=fd.get_token_id(fd.sos),
            eos_id=fd.get_token_id(fd.eos),
            pad_id=fd.get_token_id(fd.pad)),
        inverse_transform_fn=fd.get_label_encoder().inverse_transform)
