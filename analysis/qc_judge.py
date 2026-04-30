"""
QC 판정 로직
GQN, RIN, Library Size 등을 기준으로 Pass/Warning/Fail 판정
"""
import logging
from typing import Dict, Optional
from config.settings import QC_CRITERIA

logger = logging.getLogger(__name__)


class QCJudge:
    """QC 판정 클래스"""
    
    def __init__(self):
        self.criteria = QC_CRITERIA
    
    def judge_qc(self, sample_type: str, qc_data: Dict) -> str:
        """
        QC 데이터 판정
        
        Args:
            sample_type: 샘플 타입 (WGS, mRNA-seq 등)
            qc_data: QC 측정 데이터
            
        Returns:
            'Pass', 'Warning', 'Fail' 중 하나
        """
        try:
            if sample_type == "WGS":
                return self._judge_wgs(qc_data)
            elif sample_type == "mRNA-seq":
                return self._judge_mrna(qc_data)
            else:
                return self._judge_generic(qc_data)
        except Exception as e:
            logger.error(f"QC judgment failed: {e}")
            return "Pending"
    
    def _judge_wgs(self, qc_data: Dict) -> str:
        """WGS 샘플 판정 — GQN(Femto Pulse)만 판정에 사용, 농도는 참고용"""
        gqn = qc_data.get('gqn_rin')
        criteria = self.criteria.get('WGS', {})

        if gqn is not None:
            gqn_pass = criteria.get('GQN', {}).get('pass', 7.0)
            gqn_warning = criteria.get('GQN', {}).get('warning', 5.0)
            if gqn < gqn_warning:
                return "Fail"
            elif gqn < gqn_pass:
                return "Warning"

        return "Pass"

    def _judge_mrna(self, qc_data: Dict) -> str:
        """mRNA-seq 샘플 판정 — RQN/RIN(Femto Pulse)만 판정에 사용
        농도·260/280·260/230은 참고용이므로 판정에서 제외"""
        criteria = self.criteria.get('mRNA-seq', {})

        rin = qc_data.get('gqn_rin')
        if rin is None:
            return "Pending"

        rin_c = criteria.get('RIN', {})
        if rin < rin_c.get('warning', 6.0):
            return "Fail"
        elif rin < rin_c.get('pass', 8.0):
            return "Warning"
        return "Pass"
    
    def _judge_generic(self, qc_data: Dict) -> str:
        """일반 샘플 판정 (농도 기준)"""
        concentration = qc_data.get('concentration')
        
        if concentration is None:
            return "Pending"
        
        if concentration < 1.0:
            return "Warning"
        elif concentration < 0.5:
            return "Fail"
        else:
            return "Pass"
    
    def get_judgment_details(self, sample_type: str, qc_data: Dict) -> Dict:
        """
        판정 세부 정보 반환
        
        Returns:
            {
                'status': 'Pass/Warning/Fail',
                'reasons': ['이유1', '이유2', ...],
                'suggestions': ['제안1', '제안2', ...]
            }
        """
        status = self.judge_qc(sample_type, qc_data)
        reasons = []
        suggestions = []
        
        if sample_type == "WGS":
            gqn = qc_data.get('gqn_rin')

            if gqn is not None:
                if gqn < 5.0:
                    reasons.append(f"GQN too low: {gqn:.1f} (< 5.0)")
                    suggestions.append("DNA may be degraded. Consider re-extraction.")
                elif gqn < 7.0:
                    reasons.append(f"GQN marginal: {gqn:.1f} (< 7.0)")
                    suggestions.append("Proceed with caution. Monitor sequencing quality.")
        
        elif sample_type == "mRNA-seq":
            criteria = self.criteria.get('mRNA-seq', {})
            rin = qc_data.get('gqn_rin')
            p280 = qc_data.get('purity_260_280')
            p230 = qc_data.get('purity_260_230')

            if rin is not None:
                rin_warn = criteria.get('RIN', {}).get('warning', 6.0)
                rin_pass = criteria.get('RIN', {}).get('pass', 8.0)
                if rin < rin_warn:
                    reasons.append(f"RIN too low: {rin:.1f} (< {rin_warn})")
                    suggestions.append("RNA is degraded. Not suitable for mRNA-seq.")
                elif rin < rin_pass:
                    reasons.append(f"RIN suboptimal: {rin:.1f} (< {rin_pass})")
                    suggestions.append("Can proceed but expect reduced library complexity.")

            # 참고 정보 (판정에는 미사용)
            if p280 is not None:
                p_warn = criteria.get('purity_260_280', {}).get('warning', 1.8)
                p_pass = criteria.get('purity_260_280', {}).get('pass', 2.0)
                if p280 < p_warn:
                    reasons.append(f"[참고] 260/280 낮음: {p280:.2f} (기준 {p_warn})")
                elif p280 < p_pass:
                    reasons.append(f"[참고] 260/280 경계: {p280:.2f} (기준 {p_pass})")

            if p230 is not None:
                p_warn = criteria.get('purity_260_230', {}).get('warning', 1.5)
                p_pass = criteria.get('purity_260_230', {}).get('pass', 1.8)
                if p230 < p_warn:
                    reasons.append(f"[참고] 260/230 낮음: {p230:.2f} (기준 {p_warn})")
                elif p230 < p_pass:
                    reasons.append(f"[참고] 260/230 경계: {p230:.2f} (기준 {p_pass})")
        
        return {
            'status': status,
            'reasons': reasons if reasons else ['All metrics within acceptable range'],
            'suggestions': suggestions if suggestions else ['Proceed to next step']
        }


# 전역 인스턴스
qc_judge = QCJudge()


# 편의 함수
def judge_qc_metric(sample_type: str, qc_data: Dict) -> str:
    """QC 판정 헬퍼 함수"""
    return qc_judge.judge_qc(sample_type, qc_data)


def get_qc_details(sample_type: str, qc_data: Dict) -> Dict:
    """QC 세부 정보 헬퍼 함수"""
    return qc_judge.get_judgment_details(sample_type, qc_data)
