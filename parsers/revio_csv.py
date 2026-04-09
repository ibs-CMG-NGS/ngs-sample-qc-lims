"""
PacBio Revio Run Designer — CSV 생성 모듈

SMRTbell Adapter Index Plate 96A 매핑 (열 우선):
  bc_num = 2001 + col * 8 + row   (row: A=0…H=7, col: 01→0…12→11)
  A01=bc2001, B01=bc2002 … H01=bc2008
  A02=bc2009, B02=bc2010 … H12=bc2096
"""

INDEX_UUID = "43f950a9-8bde-3855-6b25-c13368069745"  # SMRTbell Adapters 96A

ROWS = list("ABCDEFGH")
COLS = [f"{i:02d}" for i in range(1, 13)]
SMRT_WELLS = ["1_A01", "1_B01", "1_C01", "1_D01"]


def bc_for_well(well: str) -> str:
    """Adapter plate well → bc barcode name (열 우선 배열).

    Examples: 'A01' → 'bc2001', 'B01' → 'bc2002', 'A02' → 'bc2009',
              'D04' → 'bc2028', 'H12' → 'bc2096'
    """
    row = ord(well[0].upper()) - ord('A')   # A=0 … H=7
    col = int(well[1:]) - 1                  # 01→0 … 12→11
    return f"bc{2001 + col * 8 + row}"


def generate_run_csv(run_settings: dict, cells: list) -> str:
    """Revio run design CSV 문자열 생성.

    Args:
        run_settings: {
            'run_name': str,
            'comments': str (optional),
            'plate1': str,
            'plate2': str (optional),
            'transfer_dir': str (optional),
        }
        cells: 활성 SMRT Cell 목록 (1~4개). 각 dict:
            {
                'smrt_cell': '1_A01' 등,
                'well_name': str,
                'movie_time': int (hours),
                'insert_size': int (bp),
                'concentration': int (pM),
                'kinetics': bool,
                'application': str,
                'adapter_bc': str (e.g. 'bc2044'),
            }
        # 향후 multiplexing 확장 시: cells[i]['samples'] 리스트 활용 예정

    Returns:
        CSV 문자열

    Raises:
        ValueError: cells가 비어 있을 때
    """
    if not cells:
        raise ValueError("At least one SMRT Cell must be configured.")

    n = len(cells)

    def field_row(label: str, values: list) -> str:
        return label + "," + ",".join(str(v) for v in values)

    lines = []

    # ── [Run Settings] ─────────────────────────────────────────────
    lines.append("[Run Settings]")
    lines.append("Instrument Type,Revio")
    lines.append(f"Run Name,{run_settings.get('run_name', '')}")
    comments = run_settings.get("comments", "").strip()
    if comments:
        lines.append(f"Run Comments,{comments}")
    lines.append(f"Plate 1,{run_settings.get('plate1', '')}")
    plate2 = run_settings.get("plate2", "").strip()
    if plate2:
        lines.append(f"Plate 2,{plate2}")
    transfer = run_settings.get("transfer_dir", "").strip()
    if transfer:
        lines.append(f"Transfer Subdirectory,{transfer}")
    lines.append("CSV Version,1")
    lines.append("")

    # ── [SMRT Cell Settings] ────────────────────────────────────────
    lines.append("[SMRT Cell Settings]," + ",".join(c["smrt_cell"] for c in cells))
    lines.append(field_row("Well Name",                     [c["well_name"]   for c in cells]))
    lines.append(field_row("Application",                   [c["application"] for c in cells]))
    lines.append(field_row("Library Type",                  ["Standard"] * n))
    lines.append(field_row("Movie Acquisition Time (hours)",[c["movie_time"]  for c in cells]))
    lines.append(field_row("Insert Size (bp)",              [c["insert_size"] for c in cells]))
    lines.append(field_row("Assign Data To Project",        [1] * n))
    lines.append(field_row("Library Concentration (pM)",    [c["concentration"] for c in cells]))
    lines.append(field_row("Include Base Kinetics",
                           ["TRUE" if c["kinetics"] else "FALSE" for c in cells]))
    lines.append(field_row("Indexes",                       [INDEX_UUID] * n))
    lines.append(field_row("Sample is indexed",             ["TRUE"] * n))
    lines.append(field_row("Use Adaptive Loading",          ["TRUE"] * n))
    lines.append(field_row("Consensus Mode",                ["molecule"] * n))
    lines.append("")

    # ── [Samples] ───────────────────────────────────────────────────
    lines.append("[Samples]")
    lines.append("Bio Sample Name,Plate Well,Adapter,Adapter2")
    for c in cells:
        bc = c["adapter_bc"]
        lines.append(f"{c['well_name']},{c['smrt_cell']},{bc},{bc}")
    lines.append("")

    return "\n".join(lines)
