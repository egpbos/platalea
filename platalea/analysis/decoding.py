import sys
import torch
import platalea.basic as basic
import platalea.encoders as encoders
import platalea.dataset as dataset
import os.path
import logging
import json
import numpy as np
from plotnine import *
import pandas as pd 

def phoneme_decoding():
    logging.getLogger().setLevel('INFO')
    logging.info("Loading pytorch models")
    net_rand = basic.SpeechImage(basic.DEFAULT_CONFIG).cuda()
    net_train = basic.SpeechImage(basic.DEFAULT_CONFIG)
    net_train.load_state_dict(torch.load("experiments/basic-stack/net.20.pt").state_dict())
    net_train.cuda()
    #nets = [('random', net_rand), ('trained', net_train)]
    nets = [('trained', net_train), ('random', net_rand)]
 
    result = []
    # Recurrent
    for rep, net in nets:
        with torch.no_grad():
            net.eval()
            data = phoneme_data([(rep, net)], batch_size=32) # FIXME this hack is to prevent RAM error
            logging.info("Fitting Logistic Regression for mfcc")
            acc = logreg_acc(data['mfcc']['features'], data['mfcc']['labels'])
            logging.info("Result for {}, {} = {}".format(rep, 'mfcc', acc))
            result.append(dict(model=rep, layer='mfcc', layer_id=0, acc=acc))
            for j, kind in enumerate(data[rep], start=1):
                logging.info("Fitting Logistic Regression for {}, {}".format(rep, kind))
                acc = logreg_acc(data[rep][kind]['features'], data[rep][kind]['labels'])
                logging.info("Result for {}, {} = {}".format(rep, kind, acc))
                result.append(dict(model=rep, layer=kind, layer_id=j, acc=acc))
    json.dump(result, open("experiments/basic-stack/phoneme_decoding.json", "w"), indent=True)
    data = pd.read_json("experiments/basic-stack/phoneme_decoding.json", orient='records') 
    g = ggplot(data, aes(x='layer_id', y='acc', color='model')) + geom_point(size=2) + geom_line(size=2) + ylim(0,max(data['acc'])) 
    ggsave(g, 'experiments/basic-stack/phoneme_decoding.png')
     
def phoneme_data(nets,  batch_size):
    """Generate data for training a phoneme decoding model."""
    alignment_path="/roaming/gchrupal/datasets/flickr8k/dataset.val.fa.json"
    logging.info("Loading alignments")
    data = {}
    for line in open(alignment_path):
        item = json.loads(line)
        item['audio_id'] = os.path.basename(item['audiopath'])
        data[item['audio_id']] = item
    logging.info("Loading audio features")
    val = dataset.Flickr8KData(root='/roaming/gchrupal/datasets/flickr8k/', split='val')
    # 
    alignments_all = [ data[sent['audio_id']] for sent in val ]
    alignments = [ item for item in alignments_all if np.all([word.get('start', False) for word in item['words']]) ]
    sentids = set(item['audio_id'] for item in alignments)
    audio = [ sent['audio'] for sent in val if sent['audio_id'] in sentids ]
    result = {}
    logging.info("Computing data for MFCC")
    audio_np = [ a.numpy() for a in audio]
    y, X = phoneme_activations(audio_np, alignments, index=lambda ms: ms//10)
    result['mfcc'] = check_nan(features=X, labels=y)
    for name, net in nets:
        result[name] = {}
        index = lambda ms: encoders.inout(net.SpeechEncoder.Conv, torch.tensor(ms)//10).numpy()
        try:
            logging.info("Loading activations from activations.val.{}.pt".format(name))
            activations = torch.load("activations.val.{}.pt".format(name))
        except FileNotFoundError:    
            logging.info("Computing data for {}".format(name))
            activations = collect_activations(net, audio, batch_size=batch_size)
            logging.info("Saving activations to activations.val.{}.pt".format(name))
            torch.save(activations, "activations.val.{}.pt".format(name))
        for key in activations:
            if key != 'att':
                logging.info("Computing data for {}, {}".format(name, key))
                y, X = phoneme_activations(activations[key], alignments, index=index)
                result[name][key] = check_nan(features=X, labels=y)
    return result


def collect_activations(net, audio, batch_size=32):
    data = torch.utils.data.DataLoader(dataset=audio,
                                       batch_size=batch_size,
                                       shuffle=False,
                                       num_workers=0,
                                       collate_fn=dataset.batch_audio)
    out = {}
    for au, l in data:
        act = net.SpeechEncoder.introspect(au.cuda(), l.cuda())
        for k in act:
            if k not in out:
                out[k] = []
            out[k]  += [ item.detach().cpu().numpy() for item in act[k] ]
    return out
    

def phoneme_activations(activations, alignments, index=lambda ms: ms//10):
    """Return array of phoneme labels and array of corresponding mean-pooled activation states."""
    labels = []
    states = []
    for activation, alignment in zip(activations, alignments):
        # extract phoneme labels and activations for current utterance
        y, X = zip(*list(slices(alignment, activation, index=index)))
        y = np.array(y)
        X = np.stack(X)
        labels.append(y)
        states.append(X)
    return np.concatenate(labels), np.concatenate(states)


def logreg_acc(features, labels, test_size=1/3):
    """Fit logistic regression on part of features and labels and return accuracy on the other part."""
    #TODO tune penalty parameter C
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    scaler = StandardScaler() 
    X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=test_size, random_state=123)        
    X_train = scaler.fit_transform(X_train) 
    X_test  = scaler.transform(X_test) 
    m = LogisticRegression(solver="lbfgs", multi_class='auto', max_iter=300, random_state=123, C=1.0) 
    m.fit(X_train, y_train) 
    return float(m.score(X_test, y_test))


def slices(utt, rep, index, aggregate=lambda x: x.mean(axis=0)):
    """Return sequence of slices associated with phoneme labels, given an
       alignment object `utt`, a representation array `rep`, and
       indexing function `index`, and an aggregating function\
       `aggregate`.
    """
    for phoneme in phones(utt):
        phone, start, end = phoneme
        assert index(start)<index(end)+1, "Something funny: {} {} {} {}".format(start, end, index(start), index(end))
        yield (phone, aggregate(rep[index(start):index(end)+1]))
        
def phones(utt):
    """Return sequence of phoneme labels associated with start and end
     time corresponding to the alignment JSON object `utt`.
    
    """
    for word in utt['words']:
        pos = word['start']
        for phone in word['phones']:
            start = pos
            end = pos + phone['duration']
            pos = end
            label = phone['phone'].split('_')[0]
            if label != 'oov':
                yield (label, int(start*1000), int(end*1000))
                
def check_nan(labels, features):
    # Get rid of NaNs
    ix = np.isnan(features.sum(axis=1))
    logging.info("Found {} NaNs".format(sum(ix)))
    X = features[~ix]
    y = labels[~ix]
    return dict(features=X, labels=y)
