import argparse
import os
import sys
from torchvision.utils import make_grid, save_image
import torch.nn as nn
from utils import *
from network.RCF.models import RCF
import time

def strToBool(str):
    return str.lower() in ('true', 'yes', 'on', 't', '1')
parser = argparse.ArgumentParser()
parser.register('type', 'bool', strToBool)
parser.add_argument("--out", type=str, default='results', help='path of save results')
parser.add_argument("--testset",  default='all', const='all', nargs='?', choices=['all', 'rainH', 'rainH','rainH'], help='')
parser.add_argument("--model",  default='all', const='all', nargs='?', choices=['all',
                                                                                'U',
                                                                                'U_D',
                                                                                'U_D_G',
                                                                                'U_D_ReLU_G',
                                                                                'U_D_ReLU_UG',
                                                                                'U_D_XU_UG',
                                                                                'UnfairGAN',
                                                                                'CycleGAN',
                                                                                'Pix2Pix',
                                                                                'AttenGAN',
                                                                                'RoboCar',], help='')
parser.add_argument("--save_img", type='bool', default=True, help='')
parser.add_argument("--debug", type='bool', default=False, help='')
parser.add_argument("--gpu", type='bool', default=True, help='')
parser.set_defaults(feature=True)

opt = parser.parse_args()
print(opt)

if opt.model == 'all':
    dicts = [
        # 'rain',
        # 'U',
        # 'U_D',
        # 'U_D_G',
        # 'U_D_ReLU_G',
        # 'U_D_ReLU_UG',
        # 'U_D_XU_UG',
        'UnfairGAN',
        'CycleGAN',
        'Pix2Pix',
        'AttenGAN',
        'RoboCar',
    ]
else:
    dicts = [
        opt.model,
        ]

if opt.testset == 'all':
    # testsets = [
    #     'rainH',
    #     'rainN',
    #     'rainL',]
    testsets = [
        'test_rainH',
        'test_rainN',
        'test_rainL',]
else:
    testsets = [opt.testset]

## GPU
device = torch.device("cuda:0" if (torch.cuda.is_available() and opt.gpu)else "cpu")
# device = torch.device("cpu")
results = {}

sys.stdout.write('> Run ...')
with torch.no_grad():
    inxseg_chs = 0
    for r in dicts:
        results[r] = {}
        # estNet
        from network.unfairGan import Generator
        estNet = Generator(inRM_chs=0, inED_chs=0, mainblock_type='U_D', act_type='ReLU').to(device)
        estNet = nn.DataParallel(estNet, device_ids=[device])
        estNet.load_state_dict(torch.load('weight/U_D.pth',map_location=device))
        estNet.eval()
        # rcf net
        rcfNet = RCF().to(device)
        rcfNet.load_state_dict(torch.load('weight/RCF.pth',map_location=device)['state_dict'])
        rcfNet.eval()
        # Gnet
        if 'AttenGAN' in r:
            from network.attentionGan.generator import Generator

            Gnet = Generator().to(device)
        elif 'RoboCar' in r:
            from network.RoboCar.generator import Derain_GlobalGenerator
            Gnet = Derain_GlobalGenerator(input_nc=3, output_nc=3, ngf=64, n_downsampling=4, n_blocks=9,
                                              norm_layer=nn.BatchNorm2d,
                                              padding_type='reflect').to(device)
        elif 'Pix2Pix' in r:
            from network.Pix2Pix.networks import define_G
            Gnet = define_G(3, 3, 128, 'batch', False, 'normal', 0.02, gpu_id=device)
        elif 'CycleGAN' in r:
            from network.CycleGAN.models import networks
            from network.CycleGAN.util import util 
            Gnet = networks.define_G(3, 3, 64, 'resnet_9blocks','instance', not True, 'normal', 0.02, [0])
        else:
            from network.unfairGan import Generator
            if r == 'U':
                Gnet = Generator(inRM_chs=0, inED_chs=0, mainblock_type='U', act_type='ReLU', ).to(device)
            if r == 'U_D':
                Gnet = Generator(inRM_chs=0, inED_chs=0, mainblock_type='U_D', act_type='ReLU', ).to(device)
            if r == 'U_D_G':
                Gnet = Generator(inRM_chs=0, inED_chs=0, mainblock_type='U_D', act_type='ReLU', ).to(device)
            if r == 'U_D_ReLU_G':
                Gnet = Generator(inRM_chs=1, inED_chs=3, mainblock_type='U_D', act_type='ReLU', ).to(device)
            if r == 'U_D_ReLU_UG':
                Gnet = Generator(inRM_chs=1, inED_chs=3, mainblock_type='U_D', act_type='ReLU', ).to(device)
            if r == 'U_D_XU_UG':
                Gnet = Generator(inRM_chs=1, inED_chs=3, mainblock_type='U_D', act_type='XU', ).to(device)
            if r == 'UnfairGAN':
                Gnet = Generator(inRM_chs=1, inED_chs=3, mainblock_type='U_D', act_type='DAF', ).to(device)

        if r != 'rain':
            if 'CycleGAN' in r:
                if isinstance(Gnet, torch.nn.DataParallel):
                    Gnet = Gnet.module
            else:
                Gnet = nn.DataParallel(Gnet, device_ids=[device])
            Gnet.load_state_dict(torch.load('weight/%s.pth' % r,map_location=device))
            Gnet.eval()

        for testset in testsets:
            ls = os.listdir('testsets/%s/rain' % testset)
            print(testset, len(ls))
            results[r][testset] = {'psnr': [], 'ssim': [], 'time': []}
            for i, img in enumerate(ls):
                if opt.debug and i > 0: continue
                # input
                input_cv2 = cv2.imread(os.path.join('testsets/%s/rain' % testset, img))
                input = align_to_num(input_cv2)
                input = to_tensor(input, device)
                # input align to 16
                input_a16 = align_to_num(input_cv2, 16)
                input_a16 = to_tensor(input_a16, device)
                # target
                target_cv2 = cv2.imread(os.path.join('testsets/%s/gt' % testset, img[:7] + '.png'))
                target = align_to_num(target_cv2)
                target = to_tensor(target, device)
                # target align to 16
                target_a16 = align_to_num(target_cv2, 16)
                target_a16 = to_tensor(target_a16, device)
                # initial for measurement
                cal_input = input
                cal_target = target
                start_time = time.time()

                if r in ('U_D_ReLU_G',
                        'U_D_ReLU_UG',
                        'U_D_XU_UG',
                        'UnfairGAN',):
                    # rainmap
                    est = estNet(input)
                    logimg = make_grid(est.data.clamp(0., 1.), nrow=8, normalize=False, scale_each=False)
                    est = logimg.mul_(255).add_(0.5).clamp_(0, 255).permute(1, 2, 0).to('cpu', torch.uint8).numpy()[:,
                          :, ::-1]
                    derain = align_to_num(est)
                    rainmap = make_rainmap(input_cv2, derain)
                    rainmap = to_tensor(rainmap, device)
                    # edge
                    derain = prepare_image_cv2(np.array(est, dtype=np.float32))
                    derain_in = derain.transpose((1, 2, 0))
                    scale = [0.5, 1, 1.5]
                    _, H, W = derain.shape
                    multi_fuse = np.zeros((H, W), np.float32)
                    for k in range(0, len(scale)):
                        im_ = cv2.resize(derain_in, None, fx=scale[k], fy=scale[k], interpolation=cv2.INTER_LINEAR)
                        im_ = im_.transpose((2, 0, 1))
                        edges = rcfNet(torch.unsqueeze(torch.from_numpy(im_).to(device), 0))
                        edge = torch.squeeze(edges[-1].detach()).cpu().numpy()
                        fuse = cv2.resize(edge, (W, H), interpolation=cv2.INTER_LINEAR)
                        multi_fuse += fuse
                    multi_fuse = multi_fuse / len(scale)
                    edge = (multi_fuse * 255).astype(np.uint8)
                    edge = np.stack([edge, edge, edge])
                    edge = np.array(edge).transpose(1, 2, 0)
                    edge = align_to_num(edge)
                    edge = to_tensor(edge, device)

                # output
                if r == 'rain':
                    output = input.clone()
                elif r == 'U_D_G' or r == 'U_D' or r == 'U' or 'Pix2Pix' in r:
                    output = Gnet(input)
                elif 'CycleGAN' in r:
                    cyclegan_output = Gnet(input)
                    cyclegan_output = util.tensor2im(cyclegan_output)
                    cyclegan_output = cyclegan_output[:,:,::-1]
                    cyclegan_output = align_to_num(cyclegan_output)
                    output = to_tensor(cyclegan_output, device)
                elif 'RoboCar' in r:
                    output = Gnet(input_a16)
                    cal_target = target_a16
                elif 'AttenGAN' in r:
                    output = Gnet(input)[-1]
                else:
                    output = Gnet(input, rm=rainmap, ed=edge)
                # measurement
                infer_time = (time.time() - start_time)
                psnr, ssim = batch_psnr_ssim(output.clamp(0., 1.), cal_target.clamp(0., 1.), batch_ssim=True)
                # save output
                if opt.save_img and r != 'rain':
                    os.makedirs(os.path.join('%s/%s/%s' % (opt.out,testset, r)), exist_ok=True)
                    out_path = os.path.join('%s/%s/%s/%s' % (opt.out,testset, r, img))
                    logimg = make_grid(output.data.clamp(0., 1.), nrow=8, normalize=False, scale_each=False)
                    save_image(logimg, out_path)

                results[r][testset]['psnr'].append(psnr.mean())
                results[r][testset]['ssim'].append(ssim.mean())
                results[r][testset]['time'].append(infer_time)

                print('%s,  %s,  PSNR=%.2f, SSIM=%.4f, RUNTIME=%.4f s' % (r, img, psnr, ssim, infer_time))
        # Free GPU
        if r != 'rain':
            del Gnet
            torch.cuda.empty_cache()

# done
# np.save(os.path.join('results', 'results.npy'), results)
sys.stdout.write('\n')

for testset in testsets:
    print('########   %s   #######'%testset)
    for r in dicts:
        psnr = np.array(results[r][testset]['psnr']).mean()
        ssim = np.array(results[r][testset]['ssim']).mean()
        time = np.array(results[r][testset]['time']).mean()
        print('%20s,  %s,       PSNR:%.2f, SSIM:%.4f, RUNTIME=%.4f s' % ( r, testset, psnr, ssim, time))

