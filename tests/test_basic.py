"""
테스트 스크립트 - 데이터 파서 및 분석 기능 테스트
"""
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from parsers import parse_nanodrop_file, parse_qubit_file, parse_femtopulse_file
from analysis import judge_qc_metric, calculate_molarity, get_qc_details
from database import db_manager, add_sample, add_qc_metric, get_all_samples


def test_parsers():
    """파서 테스트"""
    print("\n" + "="*60)
    print("Testing Data Parsers")
    print("="*60)
    
    examples_dir = project_root / "examples"
    
    # NanoDrop 파서 테스트
    print("\n[NanoDrop Parser]")
    nanodrop_file = examples_dir / "nanodrop_sample.csv"
    if nanodrop_file.exists():
        results = parse_nanodrop_file(str(nanodrop_file))
        for r in results:
            print(f"  {r['sample_id']}: {r['concentration']} ng/µl, "
                  f"260/280={r['purity_260_280']}")
    else:
        print(f"  File not found: {nanodrop_file}")
    
    # Qubit 파서 테스트
    print("\n[Qubit Parser]")
    qubit_file = examples_dir / "qubit_sample.csv"
    if qubit_file.exists():
        results = parse_qubit_file(str(qubit_file))
        for r in results:
            print(f"  {r['sample_id']}: {r['concentration']} ng/µl")
    else:
        print(f"  File not found: {qubit_file}")
    
    # Femto Pulse 파서 테스트
    print("\n[Femto Pulse Parser]")
    femto_file = examples_dir / "femtopulse_sample.csv"
    if femto_file.exists():
        results = parse_femtopulse_file(str(femto_file))
        for r in results:
            print(f"  {r['sample_id']}: GQN={r.get('gqn_rin')}, "
                  f"Avg Size={r.get('avg_size')} bp")
    else:
        print(f"  File not found: {femto_file}")


def test_qc_judgment():
    """QC 판정 테스트"""
    print("\n" + "="*60)
    print("Testing QC Judgment")
    print("="*60)
    
    # WGS 샘플 테스트
    print("\n[WGS Sample - Good Quality]")
    qc_data_good = {
        'gqn_rin': 8.5,
        'avg_size': 450,
        'concentration': 38.2,
        'step': 'Library'
    }
    status = judge_qc_metric('WGS', qc_data_good)
    details = get_qc_details('WGS', qc_data_good)
    print(f"  Status: {status}")
    print(f"  Reasons: {details['reasons']}")
    print(f"  Suggestions: {details['suggestions']}")
    
    # WGS 샘플 - 경고
    print("\n[WGS Sample - Warning]")
    qc_data_warning = {
        'gqn_rin': 6.5,
        'avg_size': 280,
        'concentration': 15.3,
        'step': 'Library'
    }
    status = judge_qc_metric('WGS', qc_data_warning)
    details = get_qc_details('WGS', qc_data_warning)
    print(f"  Status: {status}")
    print(f"  Reasons: {details['reasons']}")
    print(f"  Suggestions: {details['suggestions']}")
    
    # mRNA 샘플 테스트
    print("\n[mRNA Sample - Good Quality]")
    qc_data_mrna = {
        'gqn_rin': 9.2,
        'concentration': 118.6
    }
    status = judge_qc_metric('mRNA-seq', qc_data_mrna)
    details = get_qc_details('mRNA-seq', qc_data_mrna)
    print(f"  Status: {status}")
    print(f"  Reasons: {details['reasons']}")


def test_molarity_calculation():
    """Molarity 계산 테스트"""
    print("\n" + "="*60)
    print("Testing Molarity Calculation")
    print("="*60)
    
    # DNA 샘플
    print("\n[DNA Sample]")
    conc = 38.2  # ng/µl
    size = 450   # bp
    molarity = calculate_molarity(conc, size, 'DNA')
    print(f"  Concentration: {conc} ng/µl")
    print(f"  Average Size: {size} bp")
    print(f"  Molarity: {molarity} nM")
    
    # RNA 샘플
    print("\n[RNA Sample]")
    conc = 118.6
    size = 300
    molarity = calculate_molarity(conc, size, 'RNA')
    print(f"  Concentration: {conc} ng/µl")
    print(f"  Average Size: {size} bases")
    print(f"  Molarity: {molarity} nM")


def test_database():
    """데이터베이스 테스트"""
    print("\n" + "="*60)
    print("Testing Database Operations")
    print("="*60)
    
    # DB 초기화
    db_manager.initialize()
    
    # 샘플 추가
    print("\n[Adding Sample]")
    with db_manager.session_scope() as session:
        sample_data = {
            'sample_id': 'TEST_WGS_001',
            'sample_name': 'Test WGS Sample',
            'sample_type': 'WGS',
            'source': 'Test Lab',
            'description': 'Test sample for development'
        }
        sample = add_sample(session, sample_data)
        print(f"  Added: {sample.sample_id}")
        
        # QC 데이터 추가
        print("\n[Adding QC Metrics]")
        qc_data = {
            'sample_id': sample.sample_id,
            'step': 'Extraction',
            'concentration': 42.5,
            'purity_260_280': 1.87,
            'purity_260_230': 2.15,
            'instrument': 'NanoDrop',
            'status': 'Pass'
        }
        qc_metric = add_qc_metric(session, qc_data)
        print(f"  Added QC: {qc_metric.step} - {qc_metric.status}")
    
    # 샘플 조회
    print("\n[Retrieving Samples]")
    with db_manager.session_scope() as session:
        samples = get_all_samples(session)
        print(f"  Total samples: {len(samples)}")
        for s in samples:
            print(f"    - {s.sample_id} ({s.sample_type})")
    
    db_manager.close()


def main():
    """메인 테스트 함수"""
    print("\n" + "="*60)
    print("NGS Sample QC LIMS - Test Suite")
    print("="*60)
    
    try:
        test_parsers()
        test_qc_judgment()
        test_molarity_calculation()
        test_database()
        
        print("\n" + "="*60)
        print("All tests completed!")
        print("="*60)
        
    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
