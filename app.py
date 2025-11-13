import io
import math
import os
from pathlib import Path
from typing import Dict, Any
import requests
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="장보기 미션 앱", page_icon="🛒", layout="wide")

# 전역 CSS (카드/그리드/테이블 고정 높이 & 이미지 HTML 렌더링용)
GLOBAL_CSS = """
<style>
/* 제품 카드 그리드 */
.product-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.product-card {
  box-sizing: border-box;
  border: 1px solid #e9ecef;
  border-radius: 12px;
  padding: 12px;
  background: #fff;
  height: 310px;             /* 고정 카드 높이 */
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}
.product-title {
  font-weight: 700;
  font-size: 16px;
  margin: 4px 2px 6px 2px;
  line-height: 1.2;
  height: 38px;              /* 두 줄까지 고정 */
  overflow: hidden;
}
.product-price {
  font-size: 15px;
  color: #333;
  margin: 6px 2px 8px 2px;
}
.product-img-wrap {
  width: 100%;
  height: 170px;             /* 이미지 박스 고정 */
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 8px;
  background: #fafafa;
  border: 1px solid #f1f3f5;
}
.product-img-wrap img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;       /* 원본 비율 유지 */
}

/* 장바구니 표 (이미지 포함) */
.cart-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 8px;
}
.cart-table th, .cart-table td {
  border: 1px solid #e9ecef;
  padding: 8px 10px;
  text-align: left;
  vertical-align: middle;
}
.cart-table th {
  background: #f8f9fa;
  font-weight: 700;
}
.cart-thumb {
  width: 56px;
  height: 56px;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid #f1f3f5;
  background: #fff;
}
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# st.html 헬퍼: 없으면 markdown 폴백
def render_html(html: str):
    try:
        st.html(html)  # Streamlit >= 1.32
    except AttributeError:
        st.markdown(html, unsafe_allow_html=True)

# -----------------------------
# 유틸 함수
# -----------------------------
def format_won(x: float) -> str:
    try:
        n = int(round(float(x)))
    except Exception:
        n = 0
    return f"{n:,}원"

def _parse_price(v):
    if pd.isna(v):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).replace(",", "").replace("원", "").strip()
    try:
        return int(float(s))
    except Exception:
        return 0

@st.cache_data
def load_products(csv_path: str = "products.csv") -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # 표준화된 컬럼 이름 확인/정리
    rename_map = {}
    for col in df.columns:
        col_strip = str(col).strip()
        if col_strip in ["품명", "상품명", "이름", "name", "title"]:
            rename_map[col] = "품명"
        elif col_strip in ["가격", "price", "금액"]:
            rename_map[col] = "가격"
        elif col_strip.lower() in ["이미지url", "이미지", "image", "image_url", "img"]:
            rename_map[col] = "이미지url"
    df = df.rename(columns=rename_map)
    for needed in ["품명", "가격", "이미지url"]:
        if needed not in df.columns:
            raise ValueError("products.csv에는 '품명, 가격, 이미지url' 열이 반드시 있어야 합니다.")
    df["가격"] = df["가격"].apply(_parse_price)
    return df[["품명", "가격", "이미지url"]]

@st.cache_data(show_spinner=False)
def fetch_image(url: str, size=(120, 120)) -> Image.Image:
    """
    결과 PNG 생성용으로만 사용 (상품/카트 표시에는 HTML <img> 사용)
    """
    try:
        r = requests.get(url, timeout=7)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        img = Image.new("RGBA", size, (230, 230, 230, 255))
        d = ImageDraw.Draw(img)
        d.text((10, size[1]//2 - 8), "이미지\n없음", fill=(100, 100, 100))
        return img
    img.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255, 0))
    canvas.paste(img, ((size[0]-img.width)//2, (size[1]-img.height)//2))
    return canvas

# --------- 폰트 탐색 & 로딩 강화 ----------
@st.cache_data(show_spinner=False)
def find_korean_font_path() -> str | None:
    """
    NanumHumanRegular.ttf을 우선적으로 탐색.
    - st.secrets['KOREAN_FONT_PATH']
    - 현재 작업 디렉토리, 스크립트 디렉토리, ./fonts, 프로젝트 루트 하위 rglob
    - 일반 한글 폰트 후보도 보조 탐색
    """
    # 1) 사용자가 secrets에 지정한 경우
    try:
        fp = st.secrets.get("KOREAN_FONT_PATH", None)
        if fp and Path(fp).is_file():
            return str(Path(fp).resolve())
    except Exception:
        pass

    # 2) 우선 후보들
    script_dir = Path(__file__).parent.resolve()
    cwd = Path.cwd().resolve()
    candidates = [
        script_dir / "fonts" / "NanumHumanRegular.ttf",
        script_dir / "NanumHumanRegular.ttf",
        cwd / "fonts" / "NanumHumanRegular.ttf",
        cwd / "NanumHumanRegular.ttf",
    ]
    for p in candidates:
        if p.is_file():
            return str(p.resolve())

    # 3) 리포지토리 전체에서 rglob로 파일명 탐색 (비용 적음)
    root = script_dir
    for parent in script_dir.parents:
        # 상위 디렉토리 쪽에 repo 루트가 있을 수 있음
        if (parent / ".git").exists() or (parent / "requirements.txt").exists():
            root = parent
            break
    try:
        for p in root.rglob("NanumHumanRegular.ttf"):
            if p.is_file():
                return str(p.resolve())
    except Exception:
        pass

    # 4) 보조 한글 폰트 후보
    fallback_candidates = [
        script_dir / "fonts" / "NotoSansKR-Regular.otf",
        script_dir / "fonts" / "NotoSansKR-Regular.ttf",
        cwd / "fonts" / "NotoSansKR-Regular.otf",
        cwd / "fonts" / "NotoSansKR-Regular.ttf",
        Path("/System/Library/Fonts/AppleGothic.ttf"),
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/NanumGothic.ttf"),
    ]
    for p in fallback_candidates:
        if p.is_file():
            return str(p.resolve())

    return None

def get_font(prefer_size=32) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    한글 폰트: 리포지토리/시스템에서 경로를 찾아 로드. 실패 시 기본 폰트(한글 미지원 가능).
    """
    fp = find_korean_font_path()
    if fp:
        try:
            return ImageFont.truetype(fp, prefer_size)
        except Exception:
            pass
    # 마지막 폴백(한글 깨질 수 있음)
    return ImageFont.load_default()

def font_status() -> str:
    fp = find_korean_font_path()
    return fp if fp else "(찾지 못함) 기본 폰트 사용 중 - PNG의 한글이 깨질 수 있어요."

def _text_wh(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    """
    Pillow 10+ 호환: textbbox()로 텍스트 크기 계산, 실패 시 textsize() 폴백
    """
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return (right - left), (bottom - top)
    except Exception:
        return draw.textsize(text, font=font)

def make_result_image(mission_title: str, reasons: str, items: pd.DataFrame, total: int, budget: int) -> bytes:
    """
    결과 이미지를 PIL로 생성하여 PNG 바이트로 반환.
    items: 컬럼 ['이미지', '품명', '수량', '단가', '합계']
    """
    # 레이아웃 설정
    padding = 40
    line_h = 44
    thumb_size = (120, 120)
    header_h = 120
    row_h = max(thumb_size[1] + 20, line_h * 3)
    table_w = 980
    footer_h = 160
    reason_lines = [s for s in reasons.strip().split("\n")] if reasons.strip() else []
    reason_h = max(100, 26 * max(1, len(reason_lines)))

    # 전체 높이 계산
    h = header_h + 30 + len(items) * row_h + 40 + reason_h + 30 + footer_h + padding * 2
    w = table_w + padding * 2

    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # ---- 폰트(한글 지원) 로딩
    title_font = get_font(44)
    bold_font = get_font(28)
    text_font = get_font(24)
    small_font = get_font(22)

    # 헤더 (상단 중앙 정렬)
    title_text = f"미션: {mission_title}"
    tw, th = _text_wh(d, title_text, title_font)
    d.text(((w - tw) // 2, padding), title_text, font=title_font, fill=(20, 20, 20))

    y = padding + header_h

    # 테이블 헤더
    d.rectangle([(padding-10, y-12), (w-padding+10, y+40)], outline=(220, 220, 220), width=1)
    d.text((padding, y), "구매 품목", font=bold_font, fill=(30, 30, 30))
    y += 60

    # 각 아이템 행 (이미지/이름/수량/단가/합계)
    for _, row in items.iterrows():
        d.rectangle([(padding-10, y-10), (w-padding+10, y+row_h-10)], outline=(235, 235, 235), width=1)
        try:
            thumb = row["이미지"]
            if not isinstance(thumb, Image.Image):
                thumb = fetch_image(row["이미지url"], size=thumb_size)
        except Exception:
            thumb = fetch_image("", size=thumb_size)
        img.paste(thumb.convert("RGBA"), (padding, y), mask=thumb)

        x_text = padding + thumb_size[0] + 20
        d.text((x_text, y + 4), f"{row['품명']}", font=bold_font, fill=(20, 20, 20))
        d.text((x_text, y + 4 + line_h), f"수량: {row['수량']}   단가: {format_won(row['단가'])}", font=text_font, fill=(60, 60, 60))
        d.text((x_text, y + 4 + line_h*2), f"합계: {format_won(row['합계'])}", font=text_font, fill=(0, 0, 0))

        y += row_h

    # 구매 이유
    y += 10
    d.text((padding, y), "구매 이유", font=bold_font, fill=(30, 30, 30))
    y += 42
    box_top = y - 12
    d.rectangle([(padding-10, box_top), (w-padding+10, y + reason_h)], outline=(220, 220, 220), width=1)
    for i, line in enumerate(reason_lines[:20]):
        d.text((padding, y + i * 26), line, font=small_font, fill=(40, 40, 40))
    y += reason_h + 36

    # 합계/예산/차액
    spent = total
    remain = budget - total
    d.text((padding, y), f"주어진 금액: {format_won(budget)}", font=bold_font, fill=(20, 20, 20))
    d.text((padding + 360, y), f"총 사용 금액: {format_won(spent)}", font=bold_font, fill=(20, 20, 20))
    d.text((padding + 720, y), f"잔액: {format_won(remain)}", font=bold_font, fill=(0, 120, 0) if remain >= 0 else (180, 0, 0))

    # PNG로 저장
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

def init_state():
    if "step" not in st.session_state:
        st.session_state.step = "start"   # start -> shop -> result
    if "mission" not in st.session_state:
        st.session_state.mission = None
    if "budget" not in st.session_state:
        st.session_state.budget = 0
    if "cart" not in st.session_state:
        st.session_state.cart: Dict[str, Dict[str, Any]] = {}
    if "submitted" not in st.session_state:
        st.session_state.submitted = False
    if "reasons" not in st.session_state:
        st.session_state.reasons = ""

def add_to_cart(name: str, price: int, img_url: str, qty: int):
    if qty <= 0:
        return
    cart = st.session_state.cart
    if name in cart:
        cart[name]["qty"] += qty
    else:
        cart[name] = {"price": price, "img_url": img_url, "qty": qty}

def cart_total() -> int:
    return int(sum(v["price"] * v["qty"] for v in st.session_state.cart.values()))

def clear_cart():
    st.session_state.cart = {}

# -----------------------------
# 미션 정의 (+ 이모지 추가)
# -----------------------------
MISSIONS = {
    "🍛 카레 만들기": 20000,
    "🏕️ 여름캠핑 준비하기": 30000,
    "🎉 친구 생일파티 준비하기": 25000,
}

# -----------------------------
# 앱 실행
# -----------------------------
def start_page():
    st.title("🛒 장보기 미션 앱")
    st.subheader("미션을 선택하세요")

    # 폰트 상태 표시 (사이드바)
    with st.sidebar:
        st.markdown("#### 폰트 상태")
        st.code(font_status())

    cols = st.columns(len(MISSIONS))
    for i, (m, budget) in enumerate(MISSIONS.items()):
        with cols[i]:
            st.markdown(f"### {m}")
            st.markdown(f"예산: **{format_won(budget)}**")
            if st.button(f"'{m}' 미션 선택", key=f"select_{i}"):
                st.session_state.mission = m
                st.session_state.budget = budget
                st.session_state.cart = {}
                st.session_state.submitted = False
                st.session_state.reasons = ""
                st.session_state.step = "shop"

    st.info("예: 카레 만들기, 여름캠핑, 생일파티 등 다양한 상황에서 필요한 물건을 골라 보세요!")

def _product_cards_html(df_slice: pd.DataFrame) -> str:
    cards = ['<div class="product-grid">']
    for _, row in df_slice.iterrows():
        name = str(row["품명"])
        price = int(row["가격"])
        img = str(row["이미지url"])
        cards.append(f"""
        <div class="product-card">
          <div class="product-title">{name}</div>
          <div class="product-img-wrap">
            <img src="{img}" alt="{name}" loading="lazy" />
          </div>
          <div class="product-price">{format_won(price)}</div>
        </div>
        """)
    cards.append("</div>")
    return "\n".join(cards)

def _render_product_cards(df_slice: pd.DataFrame):
    render_html(_product_cards_html(df_slice))

def _render_cart_table_html(cart: Dict[str, Dict[str, Any]]):
    rows = []
    for name, v in cart.items():
        qty = int(v["qty"])
        price = int(v["price"])
        total = qty * price
        img = v["img_url"]
        rows.append(f"""
        <tr>
          <td><img class="cart-thumb" src="{img}" alt="{name}" loading="lazy" /></td>
          <td>{name}</td>
          <td>{qty}</td>
          <td>{format_won(price)}</td>
          <td>{format_won(total)}</td>
        </tr>
        """)
    html = f"""
    <table class="cart-table">
      <thead>
        <tr>
          <th>이미지</th><th>품명</th><th>수량</th><th>단가</th><th>합계</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """
    render_html(html)

def shop_page(df: pd.DataFrame):
    st.title(f"🛍️ 쇼핑 - 미션: {st.session_state.mission}")
    st.caption(f"예산: {format_won(st.session_state.budget)}")

    # 3열 그리드: 행 단위로 처리
    n_cols = 3
    rows = math.ceil(len(df) / n_cols)

    for r in range(rows):
        start = r * n_cols
        end = min((r + 1) * n_cols, len(df))
        df_slice = df.iloc[start:end]

        # HTML 카드 묶음 출력 (고정 높이 & HTML 이미지)
        _render_product_cards(df_slice)

        # 같은 순서로 각 카드 아래에 수량/담기 버튼 배치(3열)
        cols = st.columns(len(df_slice))
        for c, (_, row) in enumerate(df_slice.iterrows()):
            with cols[c]:
                qty = st.number_input("수량", min_value=0, max_value=99, value=0, step=1, key=f"qty_{start+c}")
                if st.button("장바구니 담기", key=f"add_{start+c}"):
                    add_to_cart(str(row["품명"]), int(row["가격"]), str(row["이미지url"]), int(qty))
                    st.toast(f"'{row['품명']}' {qty}개를 담았습니다.", icon="🧺")

    st.divider()

    # 장바구니 요약 (이미지 포함 HTML 테이블)
    st.subheader("🧺 장바구니")
    cart = st.session_state.cart
    if not cart:
        st.write("아직 담은 물건이 없어요.")
    else:
        _render_cart_table_html(cart)

    total = cart_total()
    remain = st.session_state.budget - total

    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        st.metric("사용한 금액", format_won(total))
    with col2:
        st.metric("남은 예산", format_won(remain), delta=None)

    with col3:
        if st.button("장바구니 비우기", type="secondary"):
            clear_cart()
            st.rerun()

    over_budget = remain < 0
    if over_budget:
        st.error("예산을 초과했습니다! 일부 물건을 빼거나 수량을 줄여 주세요.")

    # 제출하기 → 결과 페이지로 이동
    submitted = st.button("제출하기", type="primary", disabled=over_budget or (total <= 0))
    if submitted:
        st.session_state.submitted = True
        st.session_state.step = "result"
        st.rerun()

def result_page():
    st.title(f"✅ 결과 - 미션: {st.session_state.mission}")

    if not st.session_state.submitted:
        st.warning("제출 버튼을 누른 경우에만 결과 화면으로 이동할 수 있어요.")
        if st.button("쇼핑 화면으로 돌아가기"):
            st.session_state.step = "shop" if st.session_state.mission else "start"
            st.rerun()
        return

    cart = st.session_state.cart
    if not cart:
        st.info("장바구니가 비어 있습니다. 쇼핑 화면으로 돌아가 물건을 담아 주세요.")
        if st.button("쇼핑하기로 돌아가기"):
            st.session_state.step = "shop"
            st.rerun()
        return

    df_items = pd.DataFrame(
        [
            {"품명": k, "수량": v["qty"], "단가": v["price"], "합계": v["price"] * v["qty"], "이미지url": v["img_url"]}
            for k, v in cart.items()
        ]
    ).sort_values("품명")

    # PNG 품질 안정: 사전 이미지 로드
    df_items["이미지"] = df_items["이미지url"].apply(lambda u: fetch_image(u, size=(120, 120)))

    st.subheader("🧾 구매한 물건")
    _render_cart_table_html(cart)

    total = int(df_items["합계"].sum())
    remain = st.session_state.budget - total

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("주어진 금액", format_won(st.session_state.budget))
    with col2:
        st.metric("총 사용 금액", format_won(total))
    with col3:
        st.metric("잔액", format_won(remain), delta=None)

    # 구매 이유
    st.markdown("### ✍️ 구매 이유")
    st.session_state.reasons = st.text_area(
        "왜 이 물건들을 골랐나요?",
        value=st.session_state.reasons,
        placeholder="예: 카레 재료를 빠짐없이 사기 위해서, 캠핑에 필요한 기본 장비를 갖추기 위해서 등",
        height=140
    )

    # 구매 이유가 작성되면 PNG로 다운 버튼 노출
    if st.session_state.reasons.strip():
        if st.button("🖼️ PNG로 다운"):
            png_bytes = make_result_image(
                mission_title=st.session_state.mission,
                reasons=st.session_state.reasons,
                items=df_items,
                total=total,
                budget=st.session_state.budget
            )
            st.download_button(
                "이미지 다운로드 (PNG)",
                data=png_bytes,
                file_name=f"{st.session_state.mission}_결과.png",
                mime="image/png",
                type="primary"
            )
            st.success("이미지를 생성했어요! 상단의 다운로드 버튼을 눌러 저장하세요.")
    else:
        st.info("구매 이유를 작성하면 ‘PNG로 다운’ 버튼이 나타납니다.")

    st.divider()
    if st.button("처음으로 돌아가기"):
        st.session_state.step = "start"
        st.session_state.cart = {}
        st.session_state.submitted = False
        st.rerun()

def main():
    init_state()
    try:
        products = load_products("products.csv")
    except Exception as e:
        st.error(f"products.csv를 불러오는 중 오류가 발생했어요: {e}")
        st.stop()

    # 단계별 화면 전환
    if st.session_state.step == "start":
        start_page()
    elif st.session_state.step == "shop":
        if not st.session_state.mission:
            st.session_state.step = "start"
            start_page()
        else:
            shop_page(products)
    elif st.session_state.step == "result":
        result_page()
    else:
        st.session_state.step = "start"
        start_page()

if __name__ == "__main__":
    main()
