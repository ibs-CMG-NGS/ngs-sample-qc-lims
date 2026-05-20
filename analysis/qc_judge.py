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

    def _judge_by_mqi_cv(self, mqi, cv_total, criteria) -> str:
        """Worst-of MQI and %CV for Femto Pulse smear-based RNA judgment."""
        mqi_c = criteria.get('MQI', {'pass': 0.65, 'warning': 0.50})
        cv_c  = criteria.get('CV',  {'pass': 70.0,  'warning': 85.0})
        _order = {"Pass": 0, "Warning": 1, "Fail": 2}
        result = "Pass"

        if mqi is not None:
            if mqi < mqi_c.get('warning', 0.50):
                mqi_status = "Fail"
            elif mqi < mqi_c.get('pass', 0.65):
                mqi_status = "Warning"
            else:
                mqi_status = "Pass"
            if _order[mqi_status] > _order[result]:
                result = mqi_status

        if cv_total is not None:
            if cv_total > cv_c.get('warning', 85.0):
                cv_status = "Fail"
            elif cv_total > cv_c.get('pass', 70.0):
                cv_status = "Warning"
            else:
                cv_status = "Pass"
            if _order[cv_status] > _order[result]:
                result = cv_status

        return result

    def _judge_mrna(self, qc_data: Dict) -> str:
        """mRNA-seq 판정 규칙
        - Femto Pulse (RIN 있음): RIN 기준 → Fail / Warning / Pass
        - Femto Pulse smear (mqi/cv_total 있음): MQI + %CV 기준
        - Qubit / NanoDrop (total_amount 있음): 총량 기준 → Warning(< 1 µg) / Pass
        """
        criteria = self.criteria.get('mRNA-seq', {})

        rin = qc_data.get('gqn_rin')
        if rin is not None:
            rin_c = criteria.get('RIN', {})
            if rin < rin_c.get('warning', 5.0):
                return "Fail"
            elif rin < rin_c.get('pass', 7.0):
                return "Warning"
            return "Pass"

        # Femto Pulse smear-only (mRNA Elution): MQI + %CV
        mqi = qc_data.get('mqi')
        cv_total = qc_data.get('cv_total')
        if mqi is not None or cv_total is not None:
            return self._judge_by_mqi_cv(mqi, cv_total, criteria)

        # RIN 없는 경우 (Qubit / NanoDrop): total_amount 기준
        total = qc_data.get('total_amount')
        if total is not None:
            pass_thr = criteria.get('total_amount', {}).get('pass', 1000.0)
            return "Pass" if total >= pass_thr else "Warning"

        return "Pending"
    
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
                rin_warn = criteria.get('RIN', {}).get('warning', 5.0)
                rin_pass = criteria.get('RIN', {}).get('pass', 7.0)
                if rin < rin_warn:
                    reasons.append(f"RIN too low: {rin:.1f} (< {rin_warn})")
                    suggestions.append("RNA is degraded. Not suitable for mRNA-seq.")
                elif rin < rin_pass:
                    reasons.append(f"RIN suboptimal: {rin:.1f} (< {rin_pass})")
                    suggestions.append("Can proceed but expect reduced library complexity.")
            else:
                total = qc_data.get('total_amount')
                if total is not None:
                    pass_thr = criteria.get('total_amount', {}).get('pass', 1000.0)
                    if total < pass_thr:
                        reasons.append(
                            f"Total RNA low: {total:.1f} ng (< {pass_thr:.0f} ng = 1 µg)"
                        )
                        suggestions.append(
                            "Increase input RNA amount for sufficient library yield."
                        )

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
