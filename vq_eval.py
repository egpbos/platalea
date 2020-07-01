import torch
import platalea.basicvq as M
import json
import glob
from platalea.vq_encode import evaluate_zerospeech
import pathlib
from pathlib import Path
import logging
logging.basicConfig(level=logging.INFO)
import os.path

def experiments(outfile=None):
    """Return the list of directories which do not contain the result file
named `outfile`."""
    dirs = glob.glob("experiments/vq-*/")
    if outfile is None:
        return dirs
    else:
        out = []
        for d in dirs:
            path = Path(d) / outfile
            if os.path.isfile(path):
                logging.info("File {} exists, skipping directory".format(path))
            else:
                out.append(d)
        return out
                

          
def zerospeech_baseline(): 
    for modeldir in experiments("vq_base_result.json"):
        result = [ json.loads(line) for line in open(modeldir + "/result.json") ]
        best = result[0]['epoch']
        oldnet = torch.load("{}/net.{}.pt".format(modeldir, best))
        logging.info("Loading model from {} at epoch {}".format(modeldir, best))
        net = M.SpeechImage(oldnet.config)
        net.load_state_dict(oldnet.state_dict())
        net.cuda()
        encoded_dir = "{}/encoded-base/2019/english/test/".format(modeldir)
        pathlib.Path(encoded_dir).mkdir(parents=True, exist_ok=True)
        logging.info("Encoding and evaluating zerospeech data")
        scores = evaluate_zerospeech(net, outdir=encoded_dir)
        logging.info("Result: {}".format(scores['2019']['english']['scores']))
        scores['epoch' ]=  best
        scores['modelpath'] =  "{}/net.{}.pt".format(modeldir, best)
        json.dump(scores, open("{}/vq_base_result.json".format(modeldir), "w"))
   
def zerospeech():
    for modeldir in experiments("vq_result.json"):
        result = [ json.loads(line) for line in open(modeldir + "result.json") ]
        best = sorted(result, key=lambda x: x['recall']['10'], reverse=True)[0]['epoch']
        oldnet = torch.load("{}/net.{}.pt".format(modeldir, best))
        logging.info("Loading model from {} at epoch {}".format(modeldir, best))
        net = M.SpeechImage(oldnet.config)
        net.load_state_dict(oldnet.state_dict())
        net.cuda()
        encoded_dir = "{}/encoded/2019/english/test/".format(modeldir)
        pathlib.Path(encoded_dir).mkdir(parents=True, exist_ok=True)
        logging.info("Encoding and evaluating zerospeech data")
        scores = evaluate_zerospeech(net, outdir=encoded_dir)
        logging.info("Result: {}".format(scores['2019']['english']['scores']))
        scores['epoch' ]=  best
        scores['modelpath'] =  "{}/net.{}.pt".format(modeldir, best)
        json.dump(scores, open("{}/vq_result.json".format(modeldir), "w"))


def prepare_rsa():
    from prepare_flickr8k import save_data, make_factors
    for modeldir in experiments("ed_rsa.json"):
        result = [ json.loads(line) for line in open(modeldir + "result.json") ]
        best = sorted(result, key=lambda x: x['recall']['10'], reverse=True)[0]['epoch']
        oldnet = torch.load("{}/net.{}.pt".format(modeldir, best))
        logging.info("Loading model from {} at epoch {}".format(modeldir, best))
        net = M.SpeechImage(oldnet.config)
        net.load_state_dict(oldnet.state_dict())
        net.cuda()
        json.dump(make_factors(net), open("{}/downsampling_factors.json".format(modeldir), "w"))
        net = M.SpeechImage(oldnet.config)
        net_rand = M.SpeechImage(oldnet.config)
        net.load_state_dict(oldnet.state_dict())
        net.cuda()
        net_rand.cuda()
        save_data([('trained', net), ('random', net_rand)], modeldir, batch_size=8)


def rsa():
    from lyz.methods import ed_rsa
    for modeldir in experiments("ed_rsa.json"):
        logging.info("Processing {}".format(modeldir))
        cor = ed_rsa(modeldir, layers=['codebook'], test_size=1/2)
        logging.info("RSA for {}: {}".format(modeldir, json.dumps(cor, indent=2)))
        json.dump(cor, open("{}/ed_rsa.json".format(modeldir), "w"))
        


def local_diag():
    from lyz.methods import local_diagnostic
    for modeldir in experiments("local/local_diagnostic.json"):
        logging.info("Running local diagnostic on {}".format(modeldir))
        output_dir = Path(modeldir) / 'local'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logging.info("Local diagnostic")
        config = dict(directory=modeldir,
                      output=output_dir,
                      hidden=None,
                      epochs=40,
                      layers=['codebook'],
                      runs=1)
        local_diagnostic(config)