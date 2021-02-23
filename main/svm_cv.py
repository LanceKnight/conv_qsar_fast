from __future__ import print_function
import sys, os
path = os.path.abspath(os.path.join('../..', ''))
sys.path.append(path)
import statistics
from conv_qsar_fast.utils.parsing import input_to_bool
from conv_qsar_fast.utils.parse_cfg import read_config
import conv_qsar_fast.utils.reset_layers as reset_layers
import rdkit.Chem as Chem
import numpy as np
import datetime
import json
import sys
import os
import time

from conv_qsar_fast.main.test import test_model, test_embeddings_demo
from conv_qsar_fast.main.data import get_data_full

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print('Usage: {} "settings.cfg"'.format(sys.argv[0]))
		quit(1)

	# Load settings
	try:
		config = read_config(sys.argv[1])
	except:
		print('Could not read config file {}'.format(sys.argv[1]))
		quit(1)

	# Get model label
	try:
		fpath = config['IO']['model_fpath']
	except KeyError:
		print('Must specify model_fpath in IO in config')
		quit(1)

	###################################################################################
	### BUILD MODEL
	###################################################################################

	print('...building model')
	try:
		kwargs = config['ARCHITECTURE']
		if 'kernel' not in kwargs:
			kwargs['kernel'] = 'rbf' # default

		from sklearn.svm import SVR 
		if kwargs['kernel'] in ['linear', 'rbf', 'poly']:
			model = SVR(kernel = kwargs['kernel'])
		elif kwargs['kernel'] in ['tanimoto']:
			def kernel(xa, xb):
				m = xa.shape[0]
				n = xb.shape[0]
				xa = xa.astype(bool)
				xb = xb.astype(bool)
				score = np.zeros((m, n))
				for i in range(m):
					for j in range(n):
						score[i, j] = float(np.sum(np.logical_and(xa[i], xb[j])))  / np.sum(np.logical_or(xa[i], xb[j]))
				#print(score)
				return score

			model = SVR(kernel = kernel)
		else:
			raise ValueError('Unknown kernel!')


		print('...built untrained model')
	except KeyboardInterrupt:
		print('User cancelled model building')
		quit(1)


	###################################################################################
	### DEFINE DATA 
	###################################################################################

	data_kwargs = config['DATA']
	if '__name__' in data_kwargs:
		del data_kwargs['__name__'] #  from configparser
	if 'batch_size' in config['TRAINING']:
		data_kwargs['batch_size'] = int(config['TRAINING']['batch_size'])
	if 'use_fp' in config['ARCHITECTURE']:
		data_kwargs['use_fp'] = config['ARCHITECTURE']['use_fp']
	if 'shuffle_seed' in data_kwargs:
		data_kwargs['shuffle_seed'] = int(data_kwargs['shuffle_seed'])
	else:
		data_kwargs['shuffle_seed'] = int(time.time())
	if 'truncate_to' in data_kwargs:
		data_kwargs['truncate_to'] = int(data_kwargs['truncate_to'])
	if 'training_ratio' in data_kwargs:
		data_kwargs['training_ratio'] = float(data_kwargs['training_ratio'])

	if 'cv_folds' in data_kwargs:
		try:
			os.makedirs(os.path.dirname(fpath))
		except: # folder exists
			pass
		if '<this_fold>' in data_kwargs['cv_folds']:
			cv_folds = data_kwargs['cv_folds']
			total_folds = int(cv_folds.split('/')[1])
			all_cv_folds = ['{}/{}'.format(i + 1, total_folds) for i in range(total_folds)]
		else:
			all_cv_folds = [data_kwargs['cv_folds']]

	# Iterate through all folds
	ref_fpath = fpath
	MSE_lst = []
	MAE_lst = []
	SD_lst = []
	for cv_fold in all_cv_folds:
		print('Using CV fold {}'.format(cv_fold))
		data_kwargs['cv_folds'] = cv_fold
		fpath = ref_fpath.replace('<this_fold>', cv_fold.split('/')[0])
		data = get_data_full(**data_kwargs)

		# Train model
		try:
			print('...training model')
			if kwargs['kernel'] not in ['tanimoto']:# this condition was added by Lance
				model.fit([x[0] for x in data[0]['mols']], data[0]['y'])
			else:
				#print("using tanimoto train, written by Lance")
				train_x = np.array([x[0] for x in data[0]['mols']])
				train_y = np.array(data[0]['y'])
				#print(train_x.shape)
				model.fit(train_x, train_y)
			print('...trained model')
		except KeyboardInterrupt:
			pass



		###################################################################################
		### TEST MODEL
		###################################################################################

		print('...testing model')
		tstamp = datetime.datetime.utcnow().strftime('%m-%d-%Y_%H-%M')
		test_x = [x[0] for x in data[2]['mols']]
		test_y = data[2]['y']
		#print(f"test_x :{test_x}")
		if kwargs['kernel'] not in ['tanimoto']:# this condition was added by Lance
			predicted_y = model.predict(test_x)
		else:
			test_x = np.array(test_x)
			predicted_y = model.predict(test_x)
		#print(f"predict_y:{predict_y}")
		
		MSE = sum(pow((test_y - predicted_y),2))/len(test_y)
		MAE = sum(abs(test_y - predicted_y))/len(test_y)
		SD = statistics.stdev(test_y - predicted_y)
		MSE_lst.append(MSE)
		MAE_lst.append(MAE)
		SD_lst.append(SD)
	print(f"MSE:{MSE_lst}, mean_MSE: {statistics.mean(MSE_lst)}")
	print(f"MAE:{MAE_lst}, mean_MAE: {statistics.mean(MAE_lst)}")
	print(f"SD:{SD_lst}, mean_SD: {statistics.mean(SD_lst)}")
		# Need to define predict_on_batch to be compatible
		# model.predict_on_batch = model.predict
		# data_withresiduals = test_model(model, data, fpath, tstamp = tstamp,
			# batch_size = 1)
	print('...tested model')