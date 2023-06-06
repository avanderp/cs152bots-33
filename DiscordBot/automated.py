import nltk
# FIRST TIME, you'll need to run the following 3 lines.
# nltk.download('punkt')
# nltk.download('wordnet')
# nltk.download('stopwords')

from joblib import load
import numpy as np
import openai
import os
import pandas as pd
from scipy.special import softmax
# from sklearn.linear_model import LogisticRegression
import time
from typing import List

import torch
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
from keras.utils import pad_sequences
# from sklearn.model_selection import train_test_split
import preprocessor as p

from transformers import XLMModel, BertTokenizer, BertForSequenceClassification, RobertaTokenizerFast, RobertaForSequenceClassification
from transformers import AdamW
import nltk
from nltk.stem import 	WordNetLemmatizer
from nltk.stem.porter import PorterStemmer
from nltk.corpus import stopwords
stop_words = set(stopwords.words('english'))

from tqdm import tqdm, trange
import pandas as pd
import io
import numpy as np
import matplotlib.pyplot as plt
import json
import pathlib
curr_working_dir = pathlib.Path().resolve()
path_to_data_and_models = "{}/../Data_And_models/".format(curr_working_dir)
# import ensemble_model.joblib

BERT_CHECKPOINT_FILE = "BERT_base_uncased_best_model.ckpt"
ENSEMBLE_MODEL_FILE = "{}ensemble_model.joblib".format(path_to_data_and_models)

TRAIN_FILE = "{}full_train.csv".format(path_to_data_and_models) # contains examples that Chat-GPT uses to learn how to predict

MAX_LEN = 128 # used for BERT model

MAXIMUM_NUM_CHAT_GPT_MESSAGES = 2048 # maximum number of messages
NUM_REQUIRED_CHAT_GPT_MESSAGES = 2 # number of structuring messages we must include to Chat-GPT


MAX_TRAIN_ROWS = (MAXIMUM_NUM_CHAT_GPT_MESSAGES - NUM_REQUIRED_CHAT_GPT_MESSAGES) // 150


ZERO_LABEL_KEYWORD = "real"
ONE_LABEL_KEYWORD = "fake"

NO_GPT_PRED_NUM_LABEL = -1
with open("tokens.json") as f:
    tokens = json.load(f)
    openai.organization = tokens["openai_organization"]
    openai.api_key = tokens["openai_api_key"]

bert_model = BertForSequenceClassification.from_pretrained('bert-base-uncased', num_labels=2)
bert_model.load_state_dict(torch.load(BERT_CHECKPOINT_FILE, map_location=torch.device('cpu')))
bert_model.eval()
ensemble_model = load(ENSEMBLE_MODEL_FILE)

wordnet_lemmatizer = WordNetLemmatizer()
porter_stemmer  = PorterStemmer()

p.set_options(p.OPT.URL, p.OPT.EMOJI)

def text_preprocess(text, lemmatizer, stemmer):
    # text = text.strip('\xa0')
    text = p.clean(text)
    tokenization = nltk.word_tokenize(text)     
    tokenization = [w for w in tokenization if not w in stop_words]
    #   text = ' '.join([porter_stemmer.stem(w) for w in tokenization])
    #   text = ' '.join([lemmatizer.lemmatize(w) for w in tokenization])
    # text = re.sub(r'\([0-9]+\)', '', text).strip()    
    return text

tokenizer = BertTokenizer.from_pretrained('bert-base-uncased', do_lower_case=True)

def Encode_TextWithAttention(sentence,tokenizer,maxlen,padding_type='max_length',attention_mask_flag=True):
    encoded_dict = tokenizer.encode_plus(sentence, add_special_tokens=True, max_length=maxlen, truncation=True, padding=padding_type, return_attention_mask=attention_mask_flag)
    return encoded_dict['input_ids'],encoded_dict['attention_mask']

def Encode_TextWithoutAttention(sentence,tokenizer,maxlen,padding_type='max_length',attention_mask_flag=False):
    encoded_dict = tokenizer.encode_plus(sentence, add_special_tokens=True, max_length=maxlen, truncation=True, padding=padding_type, return_attention_mask=attention_mask_flag)
    return encoded_dict['input_ids']

def get_TokenizedTextWithAttentionMask(sentenceList, tokenizer):
    token_ids_list,attention_mask_list = [],[]
    for sentence in sentenceList:
        token_ids,attention_mask = Encode_TextWithAttention(sentence,tokenizer,MAX_LEN)
        token_ids_list.append(token_ids)
        attention_mask_list.append(attention_mask)
    return token_ids_list,attention_mask_list

def get_TokenizedText(sentenceList, tokenizer):
    token_ids_list = []
    for sentence in sentenceList:
        token_ids = Encode_TextWithoutAttention(sentence,tokenizer,MAX_LEN)
        token_ids_list.append(token_ids)
    return token_ids_list

def bert_preprocess(text_inputs: List, tokenizer = tokenizer, wordnet_lemmatizer = wordnet_lemmatizer, porter_stemmer = porter_stemmer):
  preprocessed_texts = []
  for text in text_inputs:
    preprocessed_texts.append(text_preprocess(text, wordnet_lemmatizer, porter_stemmer))
  
  token_ids, attention_masks = torch.tensor(get_TokenizedTextWithAttentionMask(preprocessed_texts, tokenizer))

  return token_ids, attention_masks

def generate_bert_predictions(text_inputs: List, bert_model = bert_model):
  # might need to shape into batches
  token_ids, attention_masks = bert_preprocess(text_inputs)

  output = bert_model(token_ids, token_type_ids=None, attention_mask=attention_masks)
  logits = output[0]
  
  logits = logits.detach().cpu().numpy()
  pred = np.argmax(logits, axis=1).flatten()

  # check the dimensions to make sure we're doing the right thing
  print(logits)
  score = torch.sigmoid(torch.tensor(logits)).numpy()[:,1]
  print(score)
  return pred, score

train_df = pd.read_csv(TRAIN_FILE)
gpt_messages = [{"role": "system", "content": "You are a content moderation system. Classify input as either 'real' or 'fake'. Do not use more than one word."}]
for index, row in train_df.head(MAX_TRAIN_ROWS).iterrows():
  gpt_messages.append({"role": "user", "content": f"{row['text']}"})
  gpt_messages.append({"role": "assistant", "content": f"{row['label']}"})

def clean_pred(pred):
  if pred == None:
    return pred
  cleaned = pred.lower()
  cleaned = pred.strip()
  cleaned = ''.join([i for i in cleaned if i.isalpha()])
  return cleaned

def assign_label(pred):
  if pred == ZERO_LABEL_KEYWORD:
    return 0
  elif pred == ONE_LABEL_KEYWORD:
    return 1
  elif pred != None:
    return 0.5 
  else:  # prediciton was None (gpt response was not correctly produced)
    return NO_GPT_PRED_NUM_LABEL
  
def generate_gpt_predictions(text_inputs, prefix_messages = gpt_messages):
  preds = []
  for input in text_inputs:
    messages = prefix_messages[:]
    messages.append({"role": "user", "content": f"{row['text']}"})  

    try:
      response = openai.ChatCompletion.create(
      model="gpt-3.5-turbo",
      messages=messages
      )
      
      preds.append(response['choices'][0]['message']['content'])

    except:
      preds.append(None)

  num_preds = [assign_label(clean_pred(pred)) for pred in preds]
  return num_preds

def generate_ensemble_preds_and_scores(text_inputs, ensemble_model = ensemble_model):
  bert_preds, bert_scores = generate_bert_predictions(text_inputs)
  gpt_preds = generate_gpt_predictions(text_inputs)

  ensemble_preds = []
  ensemble_scores = []
  for idx in range(len(gpt_preds)):
    if gpt_preds[idx] == NO_GPT_PRED_NUM_LABEL:
      ensemble_preds.append(bert_preds[idx])
      ensemble_scores.append(bert_scores[idx])
    else:
      ensemble_input = np.array([gpt_preds[idx], bert_preds[idx]])
      ensemble_preds.append(ensemble_model.predict(X_test))
      ensemble_preds.append(ensemble_model.predict_proba(X_test)[:, 1])

  return ensemble_preds, ensemble_scores
