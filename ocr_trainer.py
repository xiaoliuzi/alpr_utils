import os
import time
import random
import argparse
import mxnet as mx
from dataset import load_dataset, ocr_batches
from utils import Vocabulary
from ocr_net import OcrNet


def train(max_epochs, learning_rate, batch_size, max_hw, max_len, dims, fake, sgd, context):
    print("Loading dataset...", flush=True)
    dataset = load_dataset("data/train")
    vocab = Vocabulary()
    vocab.load("data/train/vocabulary.json")
    print("Vocabulary size: ", vocab.size())
    split = int(len(dataset) * 0.9)
    training_set = dataset[:split]
    print("Training set: ", len(training_set))
    validation_set = dataset[split:]
    print("Validation set: ", len(validation_set))

    model = OcrNet(max_hw, vocab.size(), max_len)
    loss = mx.gluon.loss.SoftmaxCrossEntropyLoss(axis=2)
    if os.path.isfile("model/ocr_net.params"):
        model.load_parameters("model/ocr_net.params", ctx=context)
    else:
        model.initialize(mx.init.Xavier(), ctx=context)

    print("Learning rate: ", learning_rate)
    if sgd:
        print("Optimizer: SGD")
        trainer = mx.gluon.Trainer(model.collect_params(), "SGD", {
            "learning_rate": learning_rate,
            "momentum": 0.5
        })
    else:
        print("Optimizer: Nadam")
        trainer = mx.gluon.Trainer(model.collect_params(), "Nadam", {
            "learning_rate": learning_rate
        })
    if os.path.isfile("model/ocr_net.state"):
        trainer.load_states("model/ocr_net.state")

    print("Traning...", flush=True)
    for epoch in range(max_epochs):
        ts = time.time()

        random.shuffle(training_set)
        training_total_L = 0.0
        training_batches = 0
        for x, tgt, tgt_len, lbl in ocr_batches(training_set, batch_size, dims, max_hw, fake, vocab, max_len, context):
            training_batches += 1
            with mx.autograd.record():
                y, enc_self_attn, dec_self_attn, context_attn = model(x, tgt, tgt_len)
                L = loss(y, lbl, mx.nd.not_equal(lbl, vocab.char2idx("<PAD>")).expand_dims(-1))
                L.backward()
            trainer.step(x.shape[0])
            training_batch_L = mx.nd.mean(L).asscalar()
            if training_batch_L != training_batch_L:
                raise ValueError()
            training_total_L += training_batch_L
            print("[Epoch %d  Batch %d]  batch_loss %.10f  average_loss %.10f  elapsed %.2fs" % (
                epoch, training_batches, training_batch_L, training_total_L / training_batches, time.time() - ts
            ), flush=True)
        training_avg_L = training_total_L / training_batches

        validation_total_L = 0.0
        validation_batches = 0
        for x, tgt, tgt_len, lbl in ocr_batches(validation_set, batch_size, dims, max_hw, fake, vocab, max_len, context):
            validation_batches += 1
            y, enc_self_attn, dec_self_attn, context_attn = model(x, tgt, tgt_len)
            L = loss(y, lbl, mx.nd.not_equal(lbl, vocab.char2idx("<PAD>")).expand_dims(-1))
            validation_batch_L = mx.nd.mean(L).asscalar()
            if validation_batch_L != validation_batch_L:
                raise ValueError()
            validation_total_L += validation_batch_L
        validation_avg_L = validation_total_L / validation_batches

        print("[Epoch %d]  training_loss %.10f  validation_loss %.10f  duration %.2fs" % (
            epoch + 1, training_avg_L, validation_avg_L, time.time() - ts
        ), flush=True)

        model.save_parameters("model/ocr_net.params")
        trainer.save_states("model/ocr_net.state")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start a OCR network trainer.")
    parser.add_argument("--max_epochs", help="set the max epochs (default: 100)", type=int, default=100)
    parser.add_argument("--learning_rate", help="set the learning rate (default: 0.001)", type=float, default=0.001)
    parser.add_argument("--batch_size", help="set the batch size (default: 32)", type=int, default=32)
    parser.add_argument("--img_w", help="set the max width of input images (default: 384)", type=int, default=384)
    parser.add_argument("--img_h", help="set the max height of input images (default: 128)", type=int, default=128)
    parser.add_argument("--seq_len", help="set the max length of output sequences (default: 8)", type=int, default=8)
    parser.add_argument("--dims", help="set the sample dimentions (default: 208)", type=int, default=208)
    parser.add_argument("--fake", help="set the probability of using a fake plate (default: 0.0)", type=float, default=0.0)
    parser.add_argument("--sgd", help="using sgd optimizer", action="store_true")
    parser.add_argument("--device_id", help="select device that the model using (default: 0)", type=int, default=0)
    parser.add_argument("--gpu", help="using gpu acceleration", action="store_true")
    args = parser.parse_args()

    if args.gpu:
        context = mx.gpu(args.device_id)
    else:
        context = mx.cpu(args.device_id)

    train(args.max_epochs, args.learning_rate, args.batch_size, (args.img_h, args.img_w), args.seq_len, args.dims, args.fake, args.sgd, context)