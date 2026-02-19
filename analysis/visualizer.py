"""
QC Progress 시각화 모듈
Matplotlib 기반 차트 생성
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
import logging

from config.settings import STATUS_COLORS, CHART_DPI, CHART_FIGSIZE

logger = logging.getLogger(__name__)


class QCVisualizer:
    """QC 데이터 시각화 클래스"""
    
    def __init__(self):
        self.status_colors = STATUS_COLORS
        self.dpi = CHART_DPI
        self.figsize = CHART_FIGSIZE
        
        # 한글 폰트 설정 (Windows)
        plt.rcParams['font.family'] = 'Malgun Gothic'
        plt.rcParams['axes.unicode_minus'] = False
    
    def plot_progress_chart(
        self,
        sample_id: str,
        qc_metrics: List[Dict],
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """
        샘플의 단계별 Progress Chart 생성
        
        Args:
            sample_id: 샘플 ID
            qc_metrics: QC 측정 데이터 리스트
            save_path: 저장 경로 (None이면 표시만)
            
        Returns:
            matplotlib Figure 객체
        """
        if not qc_metrics:
            logger.warning(f"No QC metrics for {sample_id}")
            return None
        
        # 데이터 준비
        steps = [qc['step'] for qc in qc_metrics]
        concentrations = [qc.get('concentration', 0) for qc in qc_metrics]
        sizes = [qc.get('avg_size', 0) for qc in qc_metrics]
        statuses = [qc.get('status', 'Pending') for qc in qc_metrics]
        
        # Figure 생성
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), dpi=self.dpi)
        
        # 1. 농도 변화 차트
        x_pos = np.arange(len(steps))
        colors = [self.status_colors.get(s, '#9E9E9E') for s in statuses]
        
        bars1 = ax1.bar(x_pos, concentrations, color=colors, alpha=0.7, edgecolor='black')
        ax1.set_xlabel('Prep Stage', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Concentration (ng/µl)', fontsize=12, fontweight='bold')
        ax1.set_title(f'QC Progress: {sample_id}', fontsize=14, fontweight='bold')
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(steps, rotation=15, ha='right')
        ax1.grid(axis='y', alpha=0.3)
        
        # 값 표시
        for i, (bar, val) in enumerate(zip(bars1, concentrations)):
            if val > 0:
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f'{val:.1f}', ha='center', va='bottom', fontsize=10)
        
        # 2. Size 변화 차트
        bars2 = ax2.bar(x_pos, sizes, color=colors, alpha=0.7, edgecolor='black')
        ax2.set_xlabel('Prep Stage', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Average Size (bp)', fontsize=12, fontweight='bold')
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(steps, rotation=15, ha='right')
        ax2.grid(axis='y', alpha=0.3)
        
        # 값 표시
        for i, (bar, val) in enumerate(zip(bars2, sizes)):
            if val > 0:
                ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f'{val:.0f}', ha='center', va='bottom', fontsize=10)
        
        # 범례 추가
        legend_elements = [
            mpatches.Patch(color=self.status_colors['Pass'], label='Pass'),
            mpatches.Patch(color=self.status_colors['Warning'], label='Warning'),
            mpatches.Patch(color=self.status_colors['Fail'], label='Fail')
        ]
        ax1.legend(handles=legend_elements, loc='upper right')
        
        plt.tight_layout()
        
        # 저장
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            logger.info(f"Progress chart saved: {save_path}")
        
        return fig
    
    def plot_sizing_overlay(
        self,
        sample_id: str,
        traces: List[Dict],
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """
        Femto Pulse Sizing 그래프 오버레이
        
        Args:
            sample_id: 샘플 ID
            traces: [{'step': str, 'time': array, 'intensity': array}, ...]
            save_path: 저장 경로
            
        Returns:
            matplotlib Figure 객체
        """
        if not traces:
            logger.warning(f"No trace data for {sample_id}")
            return None
        
        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)
        
        colors = plt.cm.tab10(np.linspace(0, 1, len(traces)))
        
        for i, trace in enumerate(traces):
            step = trace.get('step', f'Step {i+1}')
            time = trace.get('time', [])
            intensity = trace.get('intensity', [])
            
            if len(time) > 0 and len(intensity) > 0:
                ax.plot(time, intensity, label=step, color=colors[i], linewidth=2)
        
        ax.set_xlabel('Size (bp)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Intensity (FU)', fontsize=12, fontweight='bold')
        ax.set_title(f'Sizing Overlay: {sample_id}', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            logger.info(f"Sizing overlay saved: {save_path}")
        
        return fig
    
    def plot_batch_comparison(
        self,
        samples: List[Dict],
        metric: str = 'gqn_rin',
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """
        배치 내 샘플 간 비교 차트
        
        Args:
            samples: [{'sample_id': str, 'gqn_rin': float, 'status': str}, ...]
            metric: 비교할 메트릭 ('gqn_rin', 'concentration', 'avg_size')
            save_path: 저장 경로
            
        Returns:
            matplotlib Figure 객체
        """
        if not samples:
            return None
        
        sample_ids = [s['sample_id'] for s in samples]
        values = [s.get(metric, 0) for s in samples]
        statuses = [s.get('status', 'Pending') for s in samples]
        
        fig, ax = plt.subplots(figsize=(12, 6), dpi=self.dpi)
        
        x_pos = np.arange(len(sample_ids))
        colors = [self.status_colors.get(s, '#9E9E9E') for s in statuses]
        
        bars = ax.bar(x_pos, values, color=colors, alpha=0.7, edgecolor='black')
        
        # 메트릭별 레이블
        ylabel_map = {
            'gqn_rin': 'GQN / RIN',
            'concentration': 'Concentration (ng/µl)',
            'avg_size': 'Average Size (bp)'
        }
        
        ax.set_xlabel('Sample ID', fontsize=12, fontweight='bold')
        ax.set_ylabel(ylabel_map.get(metric, metric), fontsize=12, fontweight='bold')
        ax.set_title(f'Batch Comparison: {ylabel_map.get(metric, metric)}', 
                    fontsize=14, fontweight='bold')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(sample_ids, rotation=45, ha='right')
        ax.grid(axis='y', alpha=0.3)
        
        # 값 표시
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                       f'{val:.1f}', ha='center', va='bottom', fontsize=9)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            logger.info(f"Batch comparison saved: {save_path}")
        
        return fig


# 전역 인스턴스
qc_visualizer = QCVisualizer()


# 편의 함수
def create_progress_chart(sample_id: str, qc_metrics: List[Dict], save_path: str = None):
    """Progress chart 생성 헬퍼 함수"""
    return qc_visualizer.plot_progress_chart(sample_id, qc_metrics, save_path)


def create_sizing_overlay(sample_id: str, traces: List[Dict], save_path: str = None):
    """Sizing overlay 생성 헬퍼 함수"""
    return qc_visualizer.plot_sizing_overlay(sample_id, traces, save_path)


def create_batch_comparison(samples: List[Dict], metric: str = 'gqn_rin', save_path: str = None):
    """Batch comparison 생성 헬퍼 함수"""
    return qc_visualizer.plot_batch_comparison(samples, metric, save_path)
