from collections import Counter
import json
import logging
import torch
import torch.nn as nn
import torch.optim as optim

from platalea.basic import cyclic_scheduler
from platalea.encoders import SpeechEncoderBottom, SpeechEncoderSplit
from platalea.basic import SpeechImage
from platalea.speech_text import SpeechText
from platalea.asr import SpeechTranscriber
import platalea.loss
import platalea.score
import platalea.hardware

_device = platalea.hardware.device()


class MTLNetASR(nn.Module):
    def __init__(self, config):
        super(MTLNetASR, self).__init__()
        self.config = config
        SharedEncoder = SpeechEncoderBottom(config['SharedEncoder'])
        SpeechEncoderSplitSI = SpeechEncoderSplit(dict(
            SpeechEncoderBottom=SharedEncoder,
            SpeechEncoderTop=config['SpeechEncoderTopSI']))
        SpeechEncoderSplitASR = SpeechEncoderSplit(dict(
            SpeechEncoderBottom=SharedEncoder,
            SpeechEncoderTop=config['SpeechEncoderTopASR']))
        self.SpeechImage = SpeechImage(dict(
            SpeechEncoder=SpeechEncoderSplitSI,
            ImageEncoder=config['ImageEncoder'],
            margin_size=config['margin_size']))
        self.SpeechTranscriber = SpeechTranscriber(dict(
            SpeechEncoder=SpeechEncoderSplitASR,
            TextDecoder=config['TextDecoder'],
            inverse_transform_fn=config['inverse_transform_fn']))
        self.lmbd = config.get('lmbd', 0.5)

    def cost(self, item):
        loss_si = self.SpeechImage.cost(item)
        loss_asr = self.SpeechTranscriber.cost(item)
        loss = self.lmbd * loss_si + (1 - self.lmbd) * loss_asr
        return loss, {'asr': loss_asr.item(), 'speech-image': loss_si.item()}


class MTLNetSpeechText(nn.Module):
    def __init__(self, config):
        super(MTLNetSpeechText, self).__init__()
        self.config = config
        SharedEncoder = SpeechEncoderBottom(config['SharedEncoder'])
        SpeechEncoderSplitSI = SpeechEncoderSplit(dict(
            SpeechEncoderBottom=SharedEncoder,
            SpeechEncoderTop=config['SpeechEncoderTopSI']))
        SpeechEncoderSplitST = SpeechEncoderSplit(dict(
            SpeechEncoderBottom=SharedEncoder,
            SpeechEncoderTop=config['SpeechEncoderTopST']))
        self.SpeechImage = SpeechImage(dict(
            SpeechEncoder=SpeechEncoderSplitSI,
            ImageEncoder=config['ImageEncoder'],
            margin_size=config['margin_size']))
        self.SpeechText = SpeechText(dict(
            SpeechEncoder=SpeechEncoderSplitST,
            TextEncoder=config['TextEncoder'],
            margin_size=config['margin_size']))
        self.lmbd = config.get('lmbd', 0.5)

    def cost(self, item):
        loss_si = self.SpeechImage.cost(item)
        loss_st = self.SpeechText.cost(item)
        loss = self.lmbd * loss_si + (1 - self.lmbd) * loss_st
        return loss, {'speech-text': loss_st.item(),
                      'speech-image': loss_si.item()}


def val_loss(net, data):
    with torch.no_grad():
        net.eval()
        result = []
        for item in data['val']:
            item = {key: value.to(_device) for key, value in item.items()}
            result.append(net.cost(item).item())
        net.train()
    return torch.tensor(result).mean()


def experiment(net, tasks, config):
    for t in tasks:
        # Preparing nets
        t['net'].to(_device)
        t['net'].train()
        # Preparing optimizer
        if 'lr' in config.keys():
            lr = config['lr']
        else:
            lr = 1.0
        t['optimizer'] = optim.Adam(t['net'].parameters(), lr=lr)
        t['scheduler'] = cyclic_scheduler(t['optimizer'],
                                          len(t['data']['train']),
                                          max_lr=config['max_lr'], min_lr=1e-6)
        t['optimizer'].zero_grad()

    with open("result.json", "w") as out:
        for epoch in range(1, config['epochs']+1):
            for t in tasks:
                t['cost'] = Counter()
            for j, items in enumerate(zip(*[t['data']['train'] for t in tasks]),
                                      start=1):
                for i_t, t in enumerate(tasks):
                    item = {key: value.to(_device) for key, value in items[i_t].items()}
                    loss = t['net'].cost(item)
                    t['optimizer'].zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(t['net'].parameters(),
                                             config['max_norm'])
                    t['optimizer'].step()
                    t['scheduler'].step()
                    t['cost'] += Counter({'cost': loss.item(), 'N': 1})
                    if j % 100 == 0:
                        logging.info("train {} {} {} {}".format(
                            t['name'], epoch, j,
                            t['cost']['cost'] / t['cost']['N']))
                    if j % 400 == 0:
                        logging.info("valid {} {} {} {}".format(
                            t['name'], epoch, j,
                            val_loss(t['net'], t['data'])))
            # Evaluation
            result = {}
            with torch.no_grad():
                net.eval()
                for t in tasks:
                    result[t['name']] = t['eval'](t['net'],
                                                  t['data']['val'].dataset)
                net.train()
            result['epoch'] = epoch
            json.dump(result, out)
            print('', file=out, flush=True)
            # Saving model
            logging.info("Saving model in net.{}.pt".format(epoch))
            torch.save(net, "net.{}.pt".format(epoch))
