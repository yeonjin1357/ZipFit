"""Read the two reviewed LH spreadsheets; preserve source rows and currency."""
from pathlib import Path
from openpyxl import load_workbook


def read_units(path: Path, layout: str):
    wb=load_workbook(path,data_only=True,read_only=True)
    ws=wb['든든전세(서울)' if layout=='seoul' else '게시용']
    rows=list(ws.values)
    if layout=='seoul':
        assert rows[6][6]=='주소' and rows[6][17]=='임대보증금'
        name_col,address_col,dong_col,ho_col,area_col,deposit_col=5,6,7,8,12,17
    elif layout=='north':
        assert rows[6][5]=='주소' and rows[6][15]=='임대보증금(원)'
        name_col,address_col,dong_col,ho_col,area_col,deposit_col=4,5,6,7,10,15
    else: raise ValueError('Unsupported reviewed layout')
    out=[]
    for rowno,row in enumerate(rows[7:],8):
        if not isinstance(row[0],int):
            if any(x is not None for x in row): raise ValueError(f'Unexpected row {rowno}')
            continue
        value=row[deposit_col]
        if type(value) not in (int,float) or value<=0 or int(value)!=value:
            raise ValueError(f'Invalid deposit row {rowno}')
        area=row[area_col]
        if not isinstance(area,(int,float)) or area<=0 or not row[address_col]: raise ValueError(f'Invalid unit row {rowno}')
        out.append({'id':str(row[0]),'name':row[name_col],'address':row[address_col].strip(),'building':str(row[dong_col] or ''),'room':str(row[ho_col]),'area':area,'deposit':int(value),'monthly_rent':0,'source_sheet':ws.title,'source_row':rowno})
    wb.close()
    if len({x['id'] for x in out})!=len(out): raise ValueError('Duplicate source unit')
    return out
