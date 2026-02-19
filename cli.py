"""
NGS Sample QC LIMS - CLI 기반 백엔드 검증 도구
"""
import sys
import os

from config.settings import SAMPLE_TYPES, QC_STEPS
from database import (
    db_manager,
    add_sample,
    get_sample_by_id,
    get_all_samples,
    add_qc_metric,
    get_qc_metrics_by_sample,
    get_latest_qc_metric,
    add_raw_trace,
)
from parsers import parse_femtopulse_file
from analysis import get_qc_details, calculate_molarity, get_pooling_volume, get_dilution_recipe


# ── helpers ──────────────────────────────────────────────────────────────

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def pause():
    input("\n[Enter]를 눌러 계속...")


def print_header(title):
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")


def choose_from_list(items, prompt="선택", allow_cancel=True):
    """번호로 항목을 선택. 취소 시 None 반환."""
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    if allow_cancel:
        print(f"  0. 취소")
    while True:
        try:
            choice = int(input(f"{prompt} > "))
        except ValueError:
            print("숫자를 입력하세요.")
            continue
        if allow_cancel and choice == 0:
            return None
        if 1 <= choice <= len(items):
            return choice - 1  # 0-based index
        print("올바른 번호를 입력하세요.")


def input_float(prompt, allow_empty=False):
    """float 입력. allow_empty=True이면 빈 값 허용(None 반환)."""
    while True:
        val = input(f"{prompt} > ").strip()
        if allow_empty and val == "":
            return None
        try:
            return float(val)
        except ValueError:
            print("숫자를 입력하세요.")


def select_sample(session):
    """등록된 샘플 목록에서 선택. sample_id 문자열 반환."""
    samples = get_all_samples(session)
    if not samples:
        print("등록된 샘플이 없습니다. 먼저 샘플을 등록하세요.")
        return None
    print("\n등록된 샘플 목록:")
    labels = [f"{s.sample_id}  |  {s.sample_name}  |  {s.sample_type}" for s in samples]
    idx = choose_from_list(labels, "샘플 선택")
    if idx is None:
        return None
    return samples[idx].sample_id


def select_step():
    """QC step 선택."""
    print("\nStep 선택:")
    idx = choose_from_list(QC_STEPS, "Step")
    if idx is None:
        return None
    return QC_STEPS[idx]


def molecule_type_for(sample_type):
    """sample_type에 따라 DNA/RNA 판별."""
    rna_types = {"mRNA-seq"}
    return "RNA" if sample_type in rna_types else "DNA"


# ── 1. 샘플 등록 ────────────────────────────────────────────────────────

def menu_add_sample():
    print_header("샘플 등록")
    sample_id = input("Sample ID > ").strip()
    if not sample_id:
        print("Sample ID는 필수입니다.")
        return
    sample_name = input("Sample Name > ").strip()

    print("\nSample Type 선택:")
    type_keys = list(SAMPLE_TYPES.keys())
    type_labels = [f"{k} ({v})" for k, v in SAMPLE_TYPES.items()]
    idx = choose_from_list(type_labels, "Type")
    if idx is None:
        return
    sample_type = type_keys[idx]

    source = input("Source (선택사항) > ").strip() or None
    description = input("Description (선택사항) > ").strip() or None

    with db_manager.session_scope() as session:
        existing = get_sample_by_id(session, sample_id)
        if existing:
            print(f"\n[오류] Sample ID '{sample_id}'는 이미 존재합니다.")
            return
        sample = add_sample(session, {
            "sample_id": sample_id,
            "sample_name": sample_name,
            "sample_type": sample_type,
            "source": source,
            "description": description,
        })
        print(f"\n[완료] 샘플 등록: {sample.sample_id} ({sample.sample_name})")


# ── 2. NanoDrop 수동 입력 ───────────────────────────────────────────────

def menu_nanodrop():
    print_header("NanoDrop 측정값 입력")
    with db_manager.session_scope() as session:
        sample_id = select_sample(session)
        if not sample_id:
            return

        conc = input_float("Concentration (ng/ul)")
        r_280 = input_float("260/280 ratio")
        r_230 = input_float("260/230 ratio", allow_empty=True)

        step = select_step()
        if not step:
            return

        qc = add_qc_metric(session, {
            "sample_id": sample_id,
            "step": step,
            "concentration": conc,
            "purity_260_280": r_280,
            "purity_260_230": r_230,
            "instrument": "NanoDrop",
        })
        print(f"\n[완료] NanoDrop QCMetric 저장 (id={qc.id}, step={step})")


# ── 3. Qubit 수동 입력 ──────────────────────────────────────────────────

def menu_qubit():
    print_header("Qubit 측정값 입력")
    with db_manager.session_scope() as session:
        sample_id = select_sample(session)
        if not sample_id:
            return

        conc = input_float("Concentration (ng/ul)")
        volume = input_float("Volume (ul)")
        total_amount = conc * volume
        print(f"  → Total amount: {total_amount:.2f} ng")

        assay_type = input("Assay Type (예: dsDNA HS, RNA HS) > ").strip() or None

        step = select_step()
        if not step:
            return

        # 이전 step의 total_amount 조회하여 recovery rate 계산
        step_idx = QC_STEPS.index(step) if step in QC_STEPS else -1
        if step_idx > 0:
            prev_step = QC_STEPS[step_idx - 1]
            prev_metrics = [
                m for m in get_qc_metrics_by_sample(session, sample_id)
                if m.step == prev_step and m.total_amount is not None
            ]
            if prev_metrics:
                prev_total = prev_metrics[-1].total_amount
                recovery = (total_amount / prev_total) * 100 if prev_total > 0 else 0
                print(f"  → Recovery rate ({prev_step} → {step}): {recovery:.1f}%")
            else:
                print(f"  → 이전 step({prev_step})의 total amount 데이터가 없어 recovery rate를 계산할 수 없습니다.")

        qc = add_qc_metric(session, {
            "sample_id": sample_id,
            "step": step,
            "concentration": conc,
            "volume": volume,
            "total_amount": total_amount,
            "instrument": "Qubit",
        })
        print(f"\n[완료] Qubit QCMetric 저장 (id={qc.id}, step={step})")
        if assay_type:
            add_raw_trace(session, {
                "sample_id": sample_id,
                "step": step,
                "instrument_name": "Qubit",
                "assay_type": assay_type,
            })


# ── 4. Femto Pulse 파일 파싱 ────────────────────────────────────────────

def menu_femtopulse():
    print_header("Femto Pulse 파일 업로드")
    file_path = input("CSV/XML 파일 경로 > ").strip().strip('"')
    if not file_path or not os.path.isfile(file_path):
        print("[오류] 유효한 파일 경로를 입력하세요.")
        return

    try:
        results = parse_femtopulse_file(file_path)
    except Exception as e:
        print(f"[오류] 파싱 실패: {e}")
        return

    if not results:
        print("파싱 결과가 없습니다.")
        return

    # 파싱 결과 테이블 출력
    print(f"\n{'Sample ID':<20} {'GQN':>8} {'Conc':>10} {'Avg Size':>10} {'Peak Size':>10}")
    print("-" * 62)
    for r in results:
        sid = r.get("sample_id", "?")
        gqn = r.get("gqn_rin")
        conc = r.get("concentration")
        avg = r.get("avg_size")
        peak = r.get("peak_size")
        print(f"{sid:<20} {_fmt(gqn):>8} {_fmt(conc):>10} {_fmt(avg):>10} {_fmt(peak):>10}")

    step = select_step()
    if not step:
        return

    with db_manager.session_scope() as session:
        saved = 0
        for r in results:
            file_sample_id = r.get("sample_id", "")
            # 매핑 확인
            mapped_id = input(
                f"\n'{file_sample_id}' → DB sample_id (Enter=동일, 's'=건너뛰기) > "
            ).strip()
            if mapped_id.lower() == "s":
                continue
            if not mapped_id:
                mapped_id = file_sample_id

            sample = get_sample_by_id(session, mapped_id)
            if not sample:
                print(f"  [경고] '{mapped_id}' 샘플이 DB에 없습니다. 건너뜁니다.")
                continue

            qc = add_qc_metric(session, {
                "sample_id": mapped_id,
                "step": step,
                "concentration": r.get("concentration"),
                "gqn_rin": r.get("gqn_rin"),
                "avg_size": r.get("avg_size"),
                "peak_size": r.get("peak_size"),
                "instrument": "Femto Pulse",
                "data_file": file_path,
            })
            add_raw_trace(session, {
                "sample_id": mapped_id,
                "step": step,
                "raw_file_path": file_path,
                "instrument_name": "Femto Pulse",
            })
            saved += 1
            print(f"  [저장] {mapped_id} → QCMetric id={qc.id}")

        print(f"\n[완료] {saved}건 저장됨")


def _fmt(val):
    """숫자 포맷 헬퍼."""
    if val is None:
        return "-"
    return f"{val:.2f}"


# ── 5. QC 판정 실행 ─────────────────────────────────────────────────────

def menu_qc_judge():
    print_header("QC 판정 실행")
    with db_manager.session_scope() as session:
        samples = get_all_samples(session)
        if not samples:
            print("등록된 샘플이 없습니다.")
            return

        print("  1. 특정 샘플")
        print("  2. 전체 샘플")
        choice = input("선택 > ").strip()

        if choice == "1":
            target = [select_sample(session)]
            if target[0] is None:
                return
        elif choice == "2":
            target = [s.sample_id for s in samples]
        else:
            return

        for sid in target:
            sample = get_sample_by_id(session, sid)
            if not sample:
                continue
            metrics = get_qc_metrics_by_sample(session, sid)
            if not metrics:
                print(f"\n{sid}: QC 데이터 없음")
                continue

            print(f"\n--- {sid} ({sample.sample_type}) ---")
            for m in metrics:
                qc_data = {
                    "gqn_rin": m.gqn_rin,
                    "avg_size": m.avg_size,
                    "concentration": m.concentration,
                    "step": m.step,
                }
                details = get_qc_details(sample.sample_type, qc_data)
                status = details.get("status", "Pending")
                reasons = details.get("reasons", [])
                suggestions = details.get("suggestions", [])

                m.status = status

                print(f"  [{m.step}] {m.instrument or '?'}: status={status}")
                for r in reasons:
                    print(f"       reason: {r}")
                for s in suggestions:
                    print(f"       suggest: {s}")

        print("\n[완료] QC 상태가 업데이트되었습니다.")


# ── 6. Molarity 계산 ────────────────────────────────────────────────────

def menu_molarity():
    print_header("Molarity 계산")
    with db_manager.session_scope() as session:
        sample_id = select_sample(session)
        if not sample_id:
            return

        sample = get_sample_by_id(session, sample_id)
        mol_type = molecule_type_for(sample.sample_type)
        latest = get_latest_qc_metric(session, sample_id)

        if not latest:
            print("QC 데이터가 없습니다.")
            return

        conc = latest.concentration
        avg_size = latest.avg_size

        if conc is None or avg_size is None:
            print(f"Concentration={_fmt(conc)}, Avg Size={_fmt(avg_size)}")
            print("두 값 모두 필요합니다. 수동 입력하시겠습니까?")
            if input("(y/n) > ").strip().lower() == "y":
                if conc is None:
                    conc = input_float("Concentration (ng/ul)")
                if avg_size is None:
                    avg_size = input_float("Average Size (bp)")
            else:
                return

        molarity = calculate_molarity(conc, avg_size, mol_type)
        print(f"\n  Sample: {sample_id} ({mol_type})")
        print(f"  Concentration: {conc:.2f} ng/ul")
        print(f"  Average Size: {avg_size:.0f} bp")
        print(f"  Molarity: {_fmt(molarity)} nM")

        if molarity is not None:
            latest.molarity = molarity

        # pooling / dilution
        target = input_float("Target molarity (nM, 빈 값=건너뛰기)", allow_empty=True)
        if target is not None and molarity is not None:
            pool_vol = get_pooling_volume(conc, avg_size, target, mol_type)
            recipe = get_dilution_recipe(conc, avg_size, target, molecule_type=mol_type)

            print(f"\n  --- Pooling ---")
            print(f"  Pooling volume (for 10 ul): {_fmt(pool_vol)} ul")

            if recipe:
                print(f"\n  --- Dilution (to {target} nM, 20 ul final) ---")
                print(f"  Sample volume: {recipe['sample_volume']:.2f} ul")
                print(f"  Buffer volume: {recipe['buffer_volume']:.2f} ul")
                print(f"  Dilution factor: {recipe['dilution_factor']:.1f}x")
            else:
                print("  Dilution 불필요 (현재 농도가 target 이하)")

        print("\n[완료]")


# ── 7. 샘플 현황 조회 ───────────────────────────────────────────────────

def menu_status():
    print_header("샘플 현황 조회")
    with db_manager.session_scope() as session:
        samples = get_all_samples(session)
        if not samples:
            print("등록된 샘플이 없습니다.")
            return

        # 전체 목록
        print(f"\n{'Sample ID':<20} {'Name':<20} {'Type':<12} {'Latest Status':<15}")
        print("-" * 70)
        for s in samples:
            latest = get_latest_qc_metric(session, s.sample_id)
            status = latest.status if latest and latest.status else "No data"
            print(f"{s.sample_id:<20} {(s.sample_name or ''):<20} {s.sample_type:<12} {status:<15}")

        # 상세 조회
        print()
        detail_id = input("상세 조회할 Sample ID (Enter=건너뛰기) > ").strip()
        if not detail_id:
            return

        sample = get_sample_by_id(session, detail_id)
        if not sample:
            print(f"'{detail_id}' 샘플을 찾을 수 없습니다.")
            return

        print(f"\n--- {sample.sample_id} ({sample.sample_name}) ---")
        print(f"  Type: {sample.sample_type}")
        print(f"  Source: {sample.source or '-'}")
        print(f"  Description: {sample.description or '-'}")
        print(f"  Created: {sample.created_at}")

        metrics = get_qc_metrics_by_sample(session, detail_id)
        if not metrics:
            print("  QC 데이터 없음")
            return

        print(f"\n  {'Step':<18} {'Instrument':<12} {'Conc':>8} {'Vol':>7} {'Total':>9} "
              f"{'Recovery':>9} {'260/280':>8} {'GQN':>8} "
              f"{'AvgSize':>8} {'Molarity':>10} {'Status':<10} {'Date'}")
        print("  " + "-" * 135)

        # step별 이전 total_amount 기록을 위한 딕셔너리
        prev_total_map = {}
        for m in metrics:
            recovery_str = "-"
            if m.total_amount is not None:
                step_idx = QC_STEPS.index(m.step) if m.step in QC_STEPS else -1
                if step_idx > 0:
                    prev_step = QC_STEPS[step_idx - 1]
                    prev_total = prev_total_map.get(prev_step)
                    if prev_total is not None and prev_total > 0:
                        recovery_str = f"{(m.total_amount / prev_total) * 100:.1f}%"
                prev_total_map[m.step] = m.total_amount

            print(f"  {m.step:<18} {(m.instrument or '-'):<12} "
                  f"{_fmt(m.concentration):>8} {_fmt(m.volume):>7} "
                  f"{_fmt(m.total_amount):>9} {recovery_str:>9} "
                  f"{_fmt(m.purity_260_280):>8} "
                  f"{_fmt(m.gqn_rin):>8} {_fmt(m.avg_size):>8} "
                  f"{_fmt(m.molarity):>10} {(m.status or '-'):<10} "
                  f"{m.measured_at.strftime('%Y-%m-%d %H:%M') if m.measured_at else '-'}")


# ── Main ─────────────────────────────────────────────────────────────────

MENU = """
=== NGS Sample QC LIMS (CLI) ===
1. 샘플 등록
2. NanoDrop 측정값 입력
3. Qubit 측정값 입력
4. Femto Pulse 파일 업로드
5. QC 판정 실행
6. Molarity 계산
7. 샘플 현황 조회
0. 종료
"""


def main():
    db_manager.initialize()
    print("DB 초기화 완료.")

    handlers = {
        "1": menu_add_sample,
        "2": menu_nanodrop,
        "3": menu_qubit,
        "4": menu_femtopulse,
        "5": menu_qc_judge,
        "6": menu_molarity,
        "7": menu_status,
    }

    while True:
        print(MENU)
        choice = input("메뉴 선택 > ").strip()
        if choice == "0":
            print("종료합니다.")
            break
        handler = handlers.get(choice)
        if handler:
            try:
                handler()
            except KeyboardInterrupt:
                print("\n작업이 취소되었습니다.")
            except Exception as e:
                print(f"\n[오류] {e}")
            pause()
        else:
            print("올바른 번호를 입력하세요.")


if __name__ == "__main__":
    main()
