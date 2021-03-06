from transformers import DistilBertModel, DistilBertTokenizer
from transformers.file_utils import cached_path
from pathlib import Path
import torch.nn as nn
import pandas as pd
import requests
import torch
import os
import re


def download_model(s3_url, model_name):
    path = "./model/"
    path_to_model = os.path.join(path, model_name)
    if not os.path.exists(path_to_model):
        print("Model weights not found, downloading from S3...")
        print(f"URL:{s3_url}")
        os.makedirs(os.path.join(path), exist_ok=True)
        filename = Path(path_to_model)
        r = requests.get(s3_url)
        filename.write_bytes(r.content)

    return path_to_model, path


pretrained_weights = 'distilbert-base-cased'

path_to_model, path = download_model("https://s3.amazonaws.com/models.huggingface.co/bert/distilbert-base-cased-pytorch_model.bin", "pytorch_model.bin")

tokenizer = DistilBertTokenizer.from_pretrained(path)
bert_model = DistilBertModel.from_pretrained(path)

labels_list = ["toxic", "severe_toxic", "obscene",
               "threat", "insult", "identity_hate"]


class linear_model(nn.Module):
    def __init__(self, bert_model, num_labels):
        super().__init__()

        embed_size = bert_model.config.hidden_size
        if pretrained_weights == 'distilbert-base-cased':
            dropout_prob = bert_model.config.dropout
        else:
            dropout_prob = bert_model.config.hidden_dropout_prob

        self.bert = bert_model

        self.pre_classifier = nn.Linear(embed_size, embed_size)

        self.dropout = nn.Dropout(0.2)

        self.classifier = nn.Linear(embed_size, num_labels)

    def forward(self, x):

        # Get BERT embeddings for input_ids
        with torch.no_grad():
            # (batch_size, seq_len, hidden_size)
            hidden = self.bert(x)[0]

        # (batch_size, hidden_size)
        hidden = hidden[:, 0]

        # (batch_size, hidden_size)
        pooled_output = self.pre_classifier(hidden)
        # (batch_size, hidden_size)
        pooled_output = nn.ReLU()(pooled_output)
        # (batch_size, hidden_size)
        pooled_output = self.dropout(pooled_output)
        # (batch_size, hidden_size)
        logits = self.classifier(pooled_output)

        return logits

if pretrained_weights == 'distilbert-base-cased':
    s3_url = 'https://toxic-model.s3.eu-west-2.amazonaws.com/distil_toxic_model.pt'
    model_name = 'distil_toxic_model.pt'
else:
    s3_url = 'https://toxic-model.s3.eu-west-2.amazonaws.com/toxic_model.pt'
    model_name = 'toxic_model.pt'

path_to_model, _ = download_model(s3_url, model_name)

model = linear_model(bert_model, len(labels_list))
model.load_state_dict(torch.load(
    path_to_model, map_location=torch.device('cpu')))


def predict(text):

    model.eval()

    text = text.lower()
    # Remove punctuation
    text = re.sub(r'[^\w\s]', '', text)
    tokenized = tokenizer.encode(text, add_special_tokens=True)
    tok_tensor = torch.tensor(tokenized)
    tok_tensor = tok_tensor.unsqueeze(0)
    logits = model(tok_tensor)
    pred = torch.sigmoid(logits)
    pred = pred.detach().cpu().numpy()

    result_df = pd.DataFrame(pred, columns=[
                             "Toxic", "Severe Toxic", "Obscene", "Threat", "Insult", "Identity Hate"])
    results = result_df.to_dict("record")
    results_list = [sorted(x.items(), key=lambda kv: kv[1],
                           reverse=True) for x in results][0]

    return text, results_list
