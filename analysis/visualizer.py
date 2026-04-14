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

from config.settings import STATUS_COLORS, CHART_DPI, CHART_FIGSIZE, DATA_DIR
from database import db_manager, get_qc_metrics_by_sample
from database.models import RawTrace

logger = logging.getLogger(__name__)


def _resolve_fp_path(stored: str | None) -> Path | None:
    """DB에 저장된 경로를 실제 파일 경로로 변환.

    - 절대 경로(기존 레코드): 그대로 반환
    - 상대 경로(새 레코드): DATA_DIR 기준으로 resolve
    """
    if not stored:
        return None
    p = Path(stored)
    return p if p.is_absolute() else DATA_DIR / p


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
        calibration: Optional[List[Dict]] = None,
        save_path: Optional[str] = None,
    ) -> Optional[plt.Figure]:
        """Electropherogram step-overlay for a single sample.

        X-axis is migration time (seconds), following the raw Femto Pulse output.
        Tick positions are placed at ladder marker times from Size Calibration,
        and labeled with their corresponding base-pair sizes — matching the
        Femto Pulse ProAnalysis display style.

        Args:
            sample_id:   Sample ID (used for plot title)
            traces:      [{'step': str, 'time_sec': ndarray, 'rfu': ndarray}, ...]
            calibration: [{'time_sec': float, 'ladder_size_bp': float}, ...]
                         from parse_size_calibration(). Drives tick placement.
            save_path:   Optional file path to save the figure.

        Returns:
            matplotlib Figure or None
        """
        if not traces:
            logger.warning(f"No electropherogram traces for {sample_id}")
            return None

        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

        n = max(len(traces), 1)
        cmap = plt.cm.tab20 if n > 10 else plt.cm.tab10
        colors = cmap(np.linspace(0, 1, n))

        # Build bp→time conversion from calibration (sorted by bp for np.interp).
        # Electropherogram X values are in bp; we convert to migration time so the
        # visual spacing matches Femto Pulse ProAnalysis (non-linear, like log-scale).
        cal_bps_arr = cal_times_arr = None
        tick_times: List[float] = []
        tick_bp_labels: List[float] = []
        if calibration:
            pts = sorted(
                [(c['ladder_size_bp'], c['time_sec']) for c in calibration
                 if c.get('ladder_size_bp') is not None and c.get('time_sec') is not None],
                key=lambda p: p[0]   # sort by bp for np.interp
            )
            if pts:
                cal_bps_arr   = np.array([p[0] for p in pts])
                cal_times_arr = np.array([p[1] for p in pts])
                tick_times     = list(cal_times_arr)
                tick_bp_labels = [p[0] for p in pts]

        def _bp_to_time(x_bp_arr):
            """bp → migration time 변환. calibration 범위 밖은 선형 외삽."""
            if cal_bps_arr is None:
                return np.asarray(x_bp_arr, dtype=float)
            # 보간 (범위 내)
            x_interp = np.interp(x_bp_arr, cal_bps_arr, cal_times_arr)
            # 오른쪽 외삽: 마지막 두 calibration 포인트의 기울기 사용
            if len(cal_bps_arr) >= 2:
                slope = ((cal_times_arr[-1] - cal_times_arr[-2]) /
                         (cal_bps_arr[-1] - cal_bps_arr[-2]))
                mask = np.asarray(x_bp_arr) > cal_bps_arr[-1]
                x_interp[mask] = (cal_times_arr[-1] +
                                  slope * (np.asarray(x_bp_arr)[mask] - cal_bps_arr[-1]))
            return x_interp

        max_data_time = None  # 실제 플롯된 데이터의 최대 x (migration time)
        for i, trace in enumerate(traces):
            step = trace.get('step', f'Step {i + 1}')
            x_bp = trace.get('time_sec') if trace.get('time_sec') is not None else trace.get('size_bp', [])
            rfu = trace.get('rfu', [])

            if len(x_bp) > 0 and len(rfu) > 0:
                if cal_bps_arr is not None:
                    x = _bp_to_time(np.asarray(x_bp, dtype=float))
                else:
                    x = np.asarray(x_bp, dtype=float)
                ax.plot(x, rfu, label=step, color=colors[i], linewidth=1.5)
                x_max = float(np.max(x))
                if max_data_time is None or x_max > max_data_time:
                    max_data_time = x_max

        # Ticks at calibration migration-time positions, labeled with bp sizes
        if tick_times:
            from matplotlib.ticker import FixedLocator, FixedFormatter
            ax.xaxis.set_major_locator(FixedLocator(tick_times))
            labels = [
                f'{int(bp):,}' if bp >= 1000 else str(int(bp))
                for bp in tick_bp_labels
            ]
            ax.xaxis.set_major_formatter(FixedFormatter(labels))
            ax.xaxis.set_minor_locator(FixedLocator([]))
            ax.tick_params(axis='x', rotation=45, labelsize=9)

            # Light vertical reference lines at each ladder marker
            for t in tick_times:
                ax.axvline(t, color='gray', linewidth=0.5,
                           linestyle='--', alpha=0.35)

            # X축 범위: 왼쪽은 LM 앞 2% 여백
            # 오른쪽은 실제 데이터 끝 vs 165kb 마커 중 큰 쪽 + 소폭 여백
            span = max(tick_times) - min(tick_times)
            left_margin = span * 0.02
            right_end = max(max_data_time or 0, max(tick_times))
            right_margin = span * 0.01
            ax.set_xlim(left=min(tick_times) - left_margin,
                        right=right_end + right_margin)

        ax.set_xlabel('Size (bp)  [migration time axis, calibrated by ladder]',
                      fontsize=10, fontweight='bold')
        ax.set_ylabel('RFU', fontsize=12, fontweight='bold')
        ax.set_title(f'Electropherogram: {sample_id}', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(axis='y', alpha=0.25)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight')
            logger.info(f"Electropherogram overlay saved: {save_path}")

        return fig


def load_electropherogram_traces(sample_id: str) -> tuple:
    """Load electropherogram traces for a sample from DB + on-demand CSV parsing.

    Returns:
        (traces, calibration) where
        traces:      [{'step': str, 'time_sec': ndarray, 'rfu': ndarray}, ...]
        calibration: [{'time_sec': float, 'ladder_size_bp': float}, ...]
                     from the Size Calibration file (empty list if unavailable)
    """
    from parsers import parse_electropherogram, parse_size_calibration
    from database.models import FemtoPulseRun

    traces = []
    calibration: List[Dict] = []
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
                electro_path = _resolve_fp_path(rt.raw_file_path)
                if not electro_path or not electro_path.exists():
                    logger.warning(f"Electropherogram file not found: {rt.raw_file_path}")
                    continue

                # Load calibration from the FemtoPulseRun that owns this electropherogram
                if not calibration:
                    fp_run = (
                        session.query(FemtoPulseRun)
                        .filter(FemtoPulseRun.electropherogram_path == rt.raw_file_path)
                        .first()
                    )
                    if fp_run and fp_run.size_calibration_path:
                        cal_path = _resolve_fp_path(fp_run.size_calibration_path)
                        if cal_path and cal_path.exists():
                            try:
                                cal_data = parse_size_calibration(str(cal_path))
                                calibration = [
                                    {'time_sec': r['time_sec'],
                                     'ladder_size_bp': r['ladder_size_bp']}
                                    for r in cal_data
                                    if r.get('time_sec') is not None
                                    and r.get('ladder_size_bp') is not None
                                ]
                            except Exception as e:
                                logger.warning(f"Failed to parse size calibration: {e}")

                try:
                    data = parse_electropherogram(str(electro_path))
                    time_sec = data['time_sec']

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
                            'time_sec': time_sec,
                            'rfu': matched_rfu,
                        })
                except Exception as e:
                    logger.warning(f"Failed to parse electropherogram {rt.raw_file_path}: {e}")

    except Exception as e:
        logger.error(f"Failed to load electropherogram traces: {e}")

    return traces, calibration


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
                                    calibration: List[Dict] = None, save_path: str = None):
    """Electropherogram overlay 생성 헬퍼 함수"""
    if traces is None:
        traces, calibration = load_electropherogram_traces(sample_id)
    return qc_visualizer.plot_electropherogram_overlay(
        sample_id, traces, calibration=calibration, save_path=save_path
    )
