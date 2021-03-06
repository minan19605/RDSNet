import numpy as np
import torch.nn as nn
from mmcv.cnn import normal_init

from ..builder import HEADS
from mmcv.cnn import ConvModule, bias_init_with_prob
from .rdsnet_head import RdsnetHead


@HEADS.register_module()
class RdsRetinaHead(RdsnetHead):

    def __init__(self,
                 num_classes,
                 in_channels,
                 rep_channels=32,
                 stacked_convs=4,
                 conv_cfg=None,
                 norm_cfg=None,
                 anchor_generator=dict(
                     type='AnchorGenerator',
                     octave_base_scale=4,
                     scales_per_octave=3,
                     ratios=[0.5, 1.0, 2.0],
                     strides=[8, 16, 32, 64, 128]),                 
                 **kwargs):
        self.stacked_convs = stacked_convs
        self.octave_base_scale = anchor_generator['octave_base_scale']
        self.scales_per_octave = anchor_generator['scales_per_octave']
        self.conv_cfg = conv_cfg
        self.norm_cfg = norm_cfg
        octave_scales = np.array(
            [2**(i / self.scales_per_octave) for i in range(self.scales_per_octave)])
        anchor_scales = octave_scales * self.octave_base_scale
        new_anchor_generator = {}
        new_anchor_generator['type'] = anchor_generator['type']
        new_anchor_generator['ratios'] = anchor_generator['ratios']
        new_anchor_generator['strides'] = anchor_generator['strides']
        new_anchor_generator['scales'] = anchor_scales
        super(RdsRetinaHead, self).__init__(
            num_classes, in_channels, rep_channels=rep_channels, anchor_generator=new_anchor_generator, **kwargs)

    def _init_layers(self):
        self.relu = nn.ReLU(inplace=True)
        self.cls_convs = nn.ModuleList()
        self.reg_convs = nn.ModuleList()
        self.rep_convs = nn.ModuleList()
        for i in range(self.stacked_convs):
            chn = self.in_channels if i == 0 else self.feat_channels
            self.cls_convs.append(
                ConvModule(
                    chn,
                    self.feat_channels,
                    3,
                    stride=1,
                    padding=1,
                    conv_cfg=self.conv_cfg,
                    norm_cfg=self.norm_cfg))
            self.reg_convs.append(
                ConvModule(
                    chn,
                    self.feat_channels,
                    3,
                    stride=1,
                    padding=1,
                    conv_cfg=self.conv_cfg,
                    norm_cfg=self.norm_cfg))
            self.rep_convs.append(
                ConvModule(
                    chn,
                    self.feat_channels,
                    3,
                    stride=1,
                    padding=1,
                    conv_cfg=self.conv_cfg,
                    norm_cfg=self.norm_cfg))
        self.retina_cls = nn.Conv2d(
            self.feat_channels,
            self.num_anchors * self.cls_out_channels,
            3,
            padding=1)
        self.retina_reg = nn.Conv2d(
            self.feat_channels, self.num_anchors * 4, 3, padding=1)
        self.retina_rep = nn.Conv2d(
            self.feat_channels, self.num_anchors * self.rep_channels * 2, 3, padding=1)

    def init_weights(self):
        for m in self.cls_convs:
            normal_init(m.conv, std=0.01)
        for m in self.reg_convs:
            normal_init(m.conv, std=0.01)
        for m in self.rep_convs:
            normal_init(m.conv, std=0.01)
        bias_cls = bias_init_with_prob(0.01)
        normal_init(self.retina_cls, std=0.01, bias=bias_cls)
        normal_init(self.retina_reg, std=0.01)
        normal_init(self.retina_rep, std=0.01)

    def forward_single(self, x):
        cls_feat = x
        reg_feat = x
        rep_feat = x
        for cls_conv in self.cls_convs:
            cls_feat = cls_conv(cls_feat)
        for reg_conv in self.reg_convs:
            reg_feat = reg_conv(reg_feat)
        for rep_conv in self.rep_convs:
            rep_feat = rep_conv(rep_feat)
        cls_score = self.retina_cls(cls_feat)
        bbox_pred = self.retina_reg(reg_feat)
        obj_rep = self.retina_rep(rep_feat)
        return cls_score, bbox_pred, obj_rep
