"""
Molarity 계산기
Qubit 농도와 Femto Pulse Average Size를 이용하여 nM 계산
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DNA_MW_PER_BP = 650    # g/mol per bp (average)
_RNA_MW_PER_BASE = 330  # g/mol per base (average)


class MolarityCalculator:
    """Molarity 계산 클래스"""

    def __init__(self):
        self.dna_mw_per_bp = _DNA_MW_PER_BP
        self.rna_mw_per_base = _RNA_MW_PER_BASE
    
    def calculate_molarity(
        self,
        concentration: float,
        avg_size: float,
        molecule_type: str = 'DNA'
    ) -> Optional[float]:
        """
        Molarity 계산
        
        Args:
            concentration: 농도 (ng/µl)
            avg_size: 평균 크기 (bp 또는 bases)
            molecule_type: 분자 타입 ('DNA' 또는 'RNA')
            
        Returns:
            Molarity (nM) 또는 None (계산 불가능 시)
        
        Formula:
            Molarity (nM) = (Concentration [ng/µl] × 10^6) / (Size [bp] × MW [g/mol/bp])
            
            DNA: MW = 650 g/mol/bp
            RNA: MW = 330 g/mol/base
        """
        if concentration is None or avg_size is None:
            logger.warning("Cannot calculate molarity: missing concentration or size")
            return None
        
        if concentration <= 0 or avg_size <= 0:
            logger.warning(f"Invalid values: conc={concentration}, size={avg_size}")
            return None
        
        try:
            # 분자량 선택
            if molecule_type.upper() == 'RNA':
                mw_per_unit = self.rna_mw_per_base
            else:
                mw_per_unit = self.dna_mw_per_bp
            
            # Molarity 계산
            # ng/µl → g/L로 변환: × 10^-9 × 10^3 = × 10^-6
            # g/L ÷ MW (g/mol) = mol/L = M
            # M × 10^9 = nM
            
            molarity_nM = (concentration * 1e6) / (avg_size * mw_per_unit)
            
            logger.debug(
                f"Molarity calculation: {concentration} ng/µl × "
                f"{avg_size} bp = {molarity_nM:.2f} nM"
            )
            
            return round(molarity_nM, 2)
            
        except Exception as e:
            logger.error(f"Molarity calculation failed: {e}")
            return None
    
    def calculate_volume_for_pooling(
        self,
        concentration: float,
        avg_size: float,
        target_molarity: float,
        target_volume: float = 10.0,
        molecule_type: str = 'DNA'
    ) -> Optional[float]:
        """
        Pooling을 위한 필요 부피 계산
        
        Args:
            concentration: 샘플 농도 (ng/µl)
            avg_size: 평균 크기 (bp)
            target_molarity: 목표 농도 (nM)
            target_volume: 목표 부피 (µl)
            molecule_type: 분자 타입
            
        Returns:
            필요한 샘플 부피 (µl)
        """
        sample_molarity = self.calculate_molarity(concentration, avg_size, molecule_type)
        
        if sample_molarity is None or sample_molarity == 0:
            return None
        
        # C1 × V1 = C2 × V2
        # V1 = (C2 × V2) / C1
        required_volume = (target_molarity * target_volume) / sample_molarity
        
        return round(required_volume, 2)
    
    def calculate_dilution(
        self,
        concentration: float,
        avg_size: float,
        target_molarity: float,
        final_volume: float = 20.0,
        molecule_type: str = 'DNA'
    ) -> Optional[dict]:
        """
        희석 레시피 계산
        
        Returns:
            {
                'sample_volume': float,  # µl
                'buffer_volume': float,  # µl
                'dilution_factor': float
            }
        """
        sample_molarity = self.calculate_molarity(concentration, avg_size, molecule_type)
        
        if sample_molarity is None or sample_molarity <= target_molarity:
            return None
        
        # 필요한 샘플 부피
        sample_volume = (target_molarity * final_volume) / sample_molarity
        buffer_volume = final_volume - sample_volume
        dilution_factor = sample_molarity / target_molarity
        
        return {
            'sample_volume': round(sample_volume, 2),
            'buffer_volume': round(buffer_volume, 2),
            'dilution_factor': round(dilution_factor, 2)
        }


# 전역 인스턴스
molarity_calculator = MolarityCalculator()


# 편의 함수
def calculate_molarity(concentration: float, avg_size: float, molecule_type: str = 'DNA') -> Optional[float]:
    """Molarity 계산 헬퍼 함수"""
    return molarity_calculator.calculate_molarity(concentration, avg_size, molecule_type)


def get_pooling_volume(
    concentration: float,
    avg_size: float,
    target_molarity: float,
    molecule_type: str = 'DNA'
) -> Optional[float]:
    """Pooling 부피 계산 헬퍼 함수"""
    return molarity_calculator.calculate_volume_for_pooling(
        concentration, avg_size, target_molarity, molecule_type=molecule_type
    )


def get_dilution_recipe(
    concentration: float,
    avg_size: float,
    target_molarity: float,
    final_volume: float = 20.0,
    molecule_type: str = 'DNA'
) -> Optional[dict]:
    """희석 레시피 헬퍼 함수"""
    return molarity_calculator.calculate_dilution(
        concentration, avg_size, target_molarity, final_volume, molecule_type
    )
