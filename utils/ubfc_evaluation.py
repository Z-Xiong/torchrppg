import math
from scipy.fftpack import fft

import cv2
import torch
import os
from skimage.util import img_as_float
import numpy as np
from scipy.signal import butter, filtfilt, detrend
from scipy import  signal
import matplotlib.pyplot as plt
from models.model import Model


m_avg = lambda t, x, w: (np.asarray([t[i] for i in range(w, len(x) - w)]),
                         np.convolve(x, np.ones((2 * w + 1,)) / (2 * w + 1),
                                     mode='valid'))


def process_pipe(data, view=False, output="", name=""):
    fs = 30  # sample rate

    # moving average
    w_size = int(fs * .5)  # width of moving window
    time = np.linspace(1, len(data), num=len(data))
    mt, ms = m_avg(time, data, w_size)  # computation of moving average

    # remove global modulation
    sign = data[w_size: -w_size] - ms

    # compute signal envelope
    analytical_signal = np.abs(signal.hilbert(sign))

    fs = 30
    w_size = int(fs)
    # moving averate of envelope
    mt_new, mov_avg = m_avg(mt, analytical_signal, w_size)

    # remove envelope
    signal_pure = sign[w_size: -w_size] / mov_avg

    if view:
        import matplotlib.pylab as plt

        fig, (ax1, ax2, ax3) = plt.subplots(nrows=3, ncols=1, figsize=(10, 8), sharex=True)
        ax1.plot(time, data, "b-", label="Original")
        ax1.legend(loc='best')
        ax1.set_title("File " + str(name) + " Raw", fontsize=14)  # , fontweight="bold")

        ax2.plot(mt, sign, 'r-', label="Pure signal")
        ax2.plot(mt_new, mov_avg, 'b-', label='Modulation', alpha=.5)
        ax2.legend(loc='best')
        ax2.set_title("Raw -> filtered", fontsize=14)  # , fontweight="bold")

        ax3.plot(mt_new, signal_pure, "g-", label="Demodulated")
        ax3.set_xlim(0, mt[-1])
        ax3.set_title("Raw -> filtered -> demodulated", fontsize=14)  # , fontweight="bold")

        ax3.set_xlabel("Time (sec)", fontsize=14)  # common axis label
        ax3.legend(loc='best')

        fig.tight_layout()
        plt.savefig(output, bbox_inches='tight')

    return mt_new, signal_pure

def mse(hr, hr_gt):
    hr_zip = zip(hr, hr_gt)
    mse = 0
    for hr, gt in hr_zip:
        mse += pow(hr-gt, 2)
    mse /=len(hr_gt)
    return mse

def rmse(hr, hr_gt):
    return math.sqrt(mse(hr, hr_gt))


def mae(hr, hr_gt):
    hr_zip = zip(hr, hr_gt)
    mae = 0
    for hr, gt in hr_zip:
        mae += abs(hr-gt)
    mae /=len(hr_gt)
    return mae

def img_process(img):
    vidLxL = img_as_float(img[:, :, :])  # img_as_float是将图像除以255,变为float型
    vidLxL = vidLxL.astype('float32')
    vidLxL[vidLxL > 1] = 1  # 把数据归一化到1/255～1之间
    vidLxL[vidLxL < (1 / 255)] = 1 / 255  # 把数据归一化到1/255～1之间
    return vidLxL


def preprocess_png2pth(path_to_png, path_to_gt,  path_to_save):
    subject = path_to_png.split('/')[-1]

    if int(subject[-2:]) in [1, 4, 5, 8, 9, 10, 11, 12, 13]:
        save_path = path_to_save

        # get GT label
        with open(path_to_gt) as f:
            gt = f.readlines()
            gtTrace = gt[0].split()
            gtHr = gt[1].split()
            float_wave = [float(i) for i in gtTrace]
            float_hr_value = [float(i) for i in gtHr]
            float_hr_value = float_hr_value[45:-45]
            mt_new, float_wave = process_pipe(float_wave, view=False, output="", name="")
        f.close()

        # save data
        pngs = os.listdir(path_to_png)
        pngs.sort()
        pngs = pngs[45:-45]
        frame_length = len(pngs)  # subject frame length
        segment_length = 240  # time length every input data
        stride = 240
        # H = [(输入大小 - 卷积核大小 + 2 * P) / 步长] + 1
        n_segment = (frame_length - segment_length) // stride + 1  # subject segment length

        for i in range(n_segment):
            data = {}
            segment_face = torch.zeros(segment_length, 3, 128, 128)
            segment_label = torch.zeros(segment_length, dtype=torch.float32)
            float_label_detrend = np.zeros(segment_length, dtype=float)
            float_hr_value_repeat = np.zeros(segment_length, dtype=float)
            for j in range(i*stride, i*stride + segment_length):
                png_path = os.path.join(path_to_png, pngs[j])
                temp_face = cv2.imread(png_path)
                temp_face = cv2.resize(temp_face, (128, 128))
                temp_face = img_process(temp_face)
                # numpy to tensor
                temp_face = torch.from_numpy(temp_face)
                # (H,W,C) -> (C,H,W)
                temp_face = torch.permute(temp_face, (2, 0, 1))
                segment_face[j - i * stride, :, :, :] = temp_face
                float_label_detrend[j - i * stride] = float_wave[j]
                float_hr_value_repeat[j - i * stride] = float_hr_value[j]
            save_pth_path = save_path + '/' + subject + '_' + str(i) + '.pth'
            data['face'] = segment_face
            # normlized wave
            # float_label_detrend = detrend(float_label_detrend, type == 'linear')
            # [b_pulse, a_pulse] = butter(3, [0.75 / fps * 2, 2.5 / fps * 2], btype='bandpass')
            # float_label_detrend = filtfilt(b_pulse, a_pulse, float_label_detrend)
            segment_label = torch.from_numpy(float_label_detrend.copy()).float()
            # d_max = segment_label.max()
            # d_min = segment_label.min()
            # segment_label = torch.sub(segment_label, d_min).true_divide(d_max - d_min)
            # segment_label = (segment_label - 0.5).true_divide(0.5)
            data['wave'] = (segment_label, int(subject[-2:]))
            # hr value
            data['value'] = float_hr_value_repeat

            torch.save(data, save_pth_path)


def evaluation(path):
    data = torch.load(path)
    input = data['face']
    input = torch.unsqueeze(input, dim=0)
    gt, subject = data['wave']
    hr_gt = np.mean(data['value'])
    gt = torch.unsqueeze(gt, dim=0)
    # inference
    ouput = model(input)
    # fig = plt.figure(1)
    # plt.plot(ouput[0, ].cpu().detach().numpy(), '-')
    # # plt.plot(gt[0, ].cpu().detach().numpy(), '--')
    # plt.draw()
    # plt.pause(2)
    # plt.close(fig)

    # cal HR use ButterFilt and FouierTransfrom
    ## ButterFilt
    ouput_wave = ouput[0,].cpu().detach().numpy()
    ouput_wave = detrend(ouput_wave, type == 'linear')
    [b_pulse, a_pulse] = butter(3, [0.75 / fps * 2, 2.5 / fps * 2], btype='bandpass')
    ouput_wave = filtfilt(b_pulse, a_pulse, ouput_wave)

    gt_wave = gt[0,].cpu().detach().numpy()
    gt_wave = detrend(gt_wave, type == 'linear')
    [b_pulse, a_pulse] = butter(3, [0.75 / fps * 2, 2.5 / fps * 2], btype='bandpass')
    gt_wave = filtfilt(b_pulse, a_pulse, gt_wave)

    # fig = plt.figure(2)
    # plt.plot(ouput_wave, '-')
    # plt.plot(gt_wave, '--')
    # plt.draw()
    # plt.pause(1)
    # plt.close(fig)
    ## FFT
    length = 240
    hr_predict = 0
    # for index, wave in enumerate([ouput_wave, gt_wave]):
    for index, wave in enumerate([ouput_wave]):
        v_fft = fft(wave)
        v_FA = np.zeros((length,))
        v_FA[0] = v_fft[0].real * v_fft[0].real
        for i in range(1, int(length / 2)):
            v_FA[i] = v_fft[i].real * v_fft[i].real + v_fft[i].imag * v_fft[i].imag
        v_FA[int(length / 2)] = v_fft[int(length / 2)].real * v_fft[int(length / 2)].real

        time = 0.0
        for i in range(0, length - 1):
            time += 33

        bottom = (int)(0.7 * time / 1000.0)
        top = (int)(2.5 * time / 1000.0)
        if top > length / 2:
            top = length / 2
        i_maxpower = 0
        maxpower = 0.0
        for i in range(bottom - 2, top - 2 + 1):
            if maxpower < v_FA[i]:
                maxpower = v_FA[i]
                i_maxpower = i

        noise_power = 0.0
        signal_power = 0.0
        signal_moment = 0.0
        for i in range(bottom, top + 1):
            if (i >= i_maxpower - 2) and (i <= i_maxpower + 2):
                signal_power += v_FA[i]
                signal_moment += i * v_FA[i]
            else:
                noise_power += v_FA[i]

        if signal_power > 0.01 and noise_power > 0.01:
            snr = 10.0 * math.log10(signal_power / noise_power) + 1
            bias = i_maxpower - (signal_moment / signal_power)
            snr *= (1.0 / (1.0 + bias * bias))

        hr = (signal_moment / signal_power) * 60000.0 / time
        hr_predict = hr
    return hr_predict, hr_gt


if __name__ == '__main__':
    fps = 30
    data_dir = "/media/pxierra/4ddb33c4-42d9-4544-b7b4-796994f061ce/data/pluse/UBFC/TDM_rppg_input"
    save_pth_dir = "/media/pxierra/4ddb33c4-42d9-4544-b7b4-796994f061ce/data/pluse/UBFC/TDM_rppg_input/DATASET_2_PTH_evaluation"
    gt_paths = os.path.join(data_dir, 'path_to_gt.txt')
    png_paths = os.path.join(data_dir, 'path_to_png.txt')
    with open(gt_paths, 'r') as f_gt:
        gt_list = f_gt.readlines()
    f_gt.close()

    with open(png_paths, 'r') as f_png:
        png_list = f_png.readlines()
    f_png.close()
    list_png_gt = zip(png_list, gt_list)
    # generate pth every person, version and second as name "p10v1_51.pth"
    for i, (png_path, gt_path) in enumerate(list_png_gt):
        preprocess_png2pth(png_path.strip(), gt_path.strip(), save_pth_dir)

    # evalution
    model_path = '/media/pxierra/4ddb33c4-42d9-4544-b7b4-796994f061ce/xiongzhuang/1-PycharmProjects/rppg_tdm_talos/saved/models/RPPG_TDM_MSELoss/0927_153337/model_best.pth'
    # load model
    model = Model()
    model = model.to('cuda:0')
    model = torch.nn.DataParallel(model, device_ids=[0, 1])
    checkpoint = torch.load(model_path)
    model.load_state_dict(checkpoint['state_dict'])
    model.eval()
    # load data
    data_list = os.listdir(save_pth_dir)
    hr_predict_dict = {'v1': [], 'v2': [], 'v3': [], 'v4': [], 'v5': [], 'v6': [], 'v7': []}
    hr_gt_dict = {'v1': [], 'v2': [], 'v3': [], 'v4': [], 'v5': [], 'v6': [], 'v7': []}
    data_list.sort()
    for data_path in data_list:
        path = os.path.join(save_pth_dir, data_path)
        # scence = data_path.split('_')[0][-2:]
        scence = 'v1'
        if data_path.split('_')[0] != 'subject11':
            hr_predict, hr_gt = evaluation(path)
            print("data_path: ", data_path, "hr predict: ", hr_predict, "hr gt: ", hr_gt)
            hr_predict_dict[f'{scence}'].append(hr_predict)
            hr_gt_dict[f'{scence}'].append(hr_gt)
    for vx in ['v1']:
        mse_result = mse(hr_predict_dict[f'{vx}'], hr_gt_dict[f'{vx}'])
        rmse_result = rmse(hr_predict_dict[f'{vx}'], hr_gt_dict[f'{vx}'])
        mae_result = mae(hr_predict_dict[f'{vx}'], hr_gt_dict[f'{vx}'])
        print(f"{vx} ", "mse: ", mse_result, "rmse: ", rmse_result, "mae: ", mae_result)