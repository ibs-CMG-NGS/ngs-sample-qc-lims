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
from database import db_manager, get_qc_metrics_by_sample
from database.models import RawTrace

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

    def plot_electropherogram_overlay(
        self,
        sample_id: str,
        traces: List[Dict],
        ladder_points: Optional[List[float]] = None,
        save_path: Optional[str] = None,
    ) -> Optional[plt.Figure]:
        """Electropherogram step-overlay for a single sample.

        Args:
            sample_id: Sample ID
            traces: [{'step': str, 'size_bp': ndarray, 'rfu': ndarray}, ...]
            ladder_points: Ladder Size(bp) values from Size Calibration for x-ticks
            save_path: Optional save path

        Returns:
            matplotlib Figure or None
        """
        if not traces:
            logger.warning(f"No electropherogram traces for {sample_id}")
            return None

        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

        colors = plt.cm.tab10(np.linspace(0, 1, max(len(traces), 1)))

        for i, trace in enumerate(traces):
            step = trace.get('step', f'Step {i + 1}')
            size_bp = trace.get('size_bp', [])
            rfu = trace.get('rfu', [])

            if len(size_bp) > 0 and len(rfu) > 0:
                ax.plot(size_bp, rfu, label=step, color=colors[i], linewidth=1.5)

        ax.set_xscale('log')

        # Ladder points as x-axis ticks
        if ladder_points:
            from matplotlib.ticker import FixedLocator, FixedFormatter
            ticks = sorted([p for p in ladder_points if p > 0])
            ax.xaxis.set_major_locator(FixedLocator(ticks))
            labels = []
            for v in ticks:
                if v >= 1000:
                    labels.append(f'{int(v):,}')
                else:
                    labels.append(str(int(v)))
            ax.xaxis.set_major_formatter(FixedFormatter(labels))
            ax.xaxis.set_minor_locator(FixedLocator([]))  # no minor ticks
            ax.tick_params(axis='x', rotation=45, labelsize=9)
            # Set x-range to ladder extent with some margin
            ax.set_xlim(min(ticks) * 0.5, max(ticks) * 2.5)

        ax.set_xlabel('Size (bp)', fontsize=12, fontweight='bold')
        ax.set_ylabel('RFU', fontsize=12, fontweight='bold')
        ax.set_title(f'Electropherogram: {sample_id}', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(alpha=0.3, which='major')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            logger.info(f"Electropherogram overlay saved: {save_path}")

        return fig


def load_electropherogram_traces(sample_id: str) -> tuple:
    """Load electropherogram traces for a sample from DB + on-demand CSV parsing.

    Returns:
        (traces, ladder_points) where
        traces: [{'step': str, 'size_bp': ndarray, 'rfu': ndarray}, ...]
        ladder_points: [float, ...] from Size Calibration or empty list
    """
    from parsers import parse_electropherogram, parse_size_calibration
    from database.models import FemtoPulseRun

    traces = []
    ladder_points = []
    try:
        with db_manager.session_scope() as session:
            raw_traces = (
                session.query(RawTrace)
                .filter(
                    RawTrace.sample_id == sample_id,
                    RawTrace.instrument_name == 'Femto Pulse',
                    RawTrace.assay_type == 'Electropherogram',
                )
                .order_by(RawTrace.created_at)
                .all()
            )

            for rt in raw_traces:
                if not rt.raw_file_path:
                    continue
                from pathlib import Path
                if not Path(rt.raw_file_path).exists():
                    logger.warning(f"Electropherogram file not found: {rt.raw_file_path}")
                    continue

                # Load ladder points from the FemtoPulseRun that owns this electropherogram
                if not ladder_points:
                    fp_run = (
                        session.query(FemtoPulseRun)
                        .filter(FemtoPulseRun.electropherogram_path == rt.raw_file_path)
                        .first()
                    )
                    if fp_run and fp_run.size_calibration_path:
                        cal_path = fp_run.size_calibration_path
                        if Path(cal_path).exists():
                            try:
                                cal_data = parse_size_calibration(cal_path)
                                ladder_points = [
                                    r['ladder_size_bp'] for r in cal_data
                                    if r.get('ladder_size_bp') is not None
                                ]
                            except Exception as e:
                                logger.warning(f"Failed to parse size calibration: {e}")

                try:
                    data = parse_electropherogram(rt.raw_file_path)
                    size_bp = data['size_bp']

                    # image_path stores the original file sample ID (e.g. "SampB1")
                    # that maps to this DB sample_id (e.g. "6238")
                    file_sid = rt.image_path  # 원본 파일 Sample ID
                    matched_rfu = None
                    for col_name, rfu_arr in data['samples'].items():
                        # 1차: 원본 파일 Sample ID로 매칭 (가장 정확)
                        if file_sid and file_sid in col_name:
                            matched_rfu = rfu_arr
                            break
                    if matched_rfu is None:
                        for col_name, rfu_arr in data['samples'].items():
                            # 2차 fallback: DB sample_id로 매칭
                            if sample_id in col_name:
                                matched_rfu = rfu_arr
                                break
                            # 3차 fallback: Samp + DB sample_id
                            if f'Samp{sample_id}' in col_name:
                                matched_rfu = rfu_arr
                                break

                    if matched_rfu is not None:
                        traces.append({
                            'step': rt.step or 'Unknown',
                            'size_bp': size_bp,
                            'rfu': matched_rfu,
                        })
                except Exception as e:
                    logger.warning(f"Failed to parse electropherogram {rt.raw_file_path}: {e}")

    except Exception as e:
        logger.error(f"Failed to load electropherogram traces: {e}")

    return traces, ladder_points


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


def create_electropherogram_overlay(sample_id: str, traces: List[Dict] = None,
                                    ladder_points: List[float] = None, save_path: str = None):
    """Electropherogram overlay 생성 헬퍼 함수"""
    if traces is None:
        traces, ladder_points = load_electropherogram_traces(sample_id)
    return qc_visualizer.plot_electropherogram_overlay(
        sample_id, traces, ladder_points=ladder_points, save_path=save_path
    )
