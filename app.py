import io
import math
from typing import Dict, Any
import re
import requests
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="장보기 미션 앱", page_icon="🛒", layout="wide")

# 공통 CSS (이미지 고정 크기 & 크롭, 카드/테이블 스타일)
st.markdown(
    """
    <style>
      .grid-3 {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 16px;
      }
      .card {
        border: 1px solid #e9ecef;
        border-radius: 14px;
        padding: 14px;
        box-shadow: 0 2px 8px rgb(0 0 0 / 4%);
        background: #fff;
        height: 100%;
      }
      .imgbox {
        width: 100%;
        height: 240px;          /* 고정 높이 */
        overflow: hidden;
        border-radius: 10px;
        background: #f6f7f9;
        display:flex; align-items:center; justify-content:center;
        margin-bottom: 10px;
      }
      .imgbox img {
        width: 100%;
        height: 100%;
        object-fit: cover;      /* 비율 유지 크롭 */
        display:block;
      }
      .pname { font-weight: 700; font-size: 1.05rem; margin: 6px 0 2px; }
      .pprice { color:#444; margin-bottom: 8px; }
      .cart-table {
        width: 100%;
        border-collapse: collapse;
      }
      .cart-table th, .cart-table td {
        border-bottom: 1px solid #eee;
        padding: 10px 8px;
        text-align: left;
        vertical-align: middle;
      }
      .cart-thumb { width: 64px; height: 64px; border-radius: 8px; object-fit: cover; display:block; }
      .reason-hint { color:#666; }
    </style>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# 유틸 함수
# -----------------------------
def format_won(x: float) -> str:
    try:
        n = int(round(float(x)))
    except Exception:
        n = 0
    return f"{n:,}원"

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
    # 가격 숫자화
    def to_price(v):
        if pd.isna(v): return 0
        if isinstance(v, (int, float)): return int(v)
        s = re.sub(r"[^\d.]", "", str(v))  # 숫자/소수점 외 제거
        try:
            return int(float(s))
        except Exception:
            return 0
    df["가격"] = df["가격"].apply(to_price)
    return df[["품명", "가격", "이미지url"]]

@st.cache_data(show_spinner=False)
def fetch_image(url: str, size=(120, 120)) -> Image.Image:
    """PNG 생성용으로만 사용 (화면 렌더링은 HTML이 담당)."""
    try:
        r = requests.get(url, timeout=7)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        img = Image.new("RGBA", size, (230, 230, 230, 255))
        d = ImageDraw.Draw(img)
        d.text((10, size[1]//2 - 10), "이미지 없음", fill=(100, 100, 100))
        return img
    # Pillow 10 호환
    try:
        RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
    except Exception:
        RESAMPLE_LANCZOS = Image.LANCZOS
    img.thumbnail(size, RESAMPLE_LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255, 0))
    canvas.paste(img, ((size[0]-img.width)//2, (size[1]-img.height)//2))
    return canvas

def get_font(prefer_size=32):
    """
    한글 폰트 우선: 프로젝트 루트/fonts/NanumHumanRegular.ttf 추가 예정.
    """
    candidates = [
        "fonts/NanumHumanRegular.ttf",     # 요청 폰트(추가 권장)
        "fonts/NotoSansCJK-Regular.otf",
        "fonts/NotoSansKR-Regular.otf",
        "fonts/NanumGothic.ttf",
        "/System/Library/Fonts/AppleGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, prefer_size)
        except Exception:
            continue
    return ImageFont.load_default()

def draw_text_with_shadow(d: ImageDraw.ImageDraw, xy, text, font, fill=(20,20,20), shadow=(0,0,0), offset=(2,2)):
    x, y = xy
    d.text((x+offset[0], y+offset[1]), text, font=font, fill=shadow)
    d.text((x, y), text, font=font, fill=fill)

def make_result_image(mission_title: str, reasons: str, items: pd.DataFrame, total: int, budget: int) -> bytes:
    """
    결과 이미지를 PIL로 생성하여 PNG 바이트로 반환.
    items: 컬럼 ['이미지', '품명', '수량', '단가', '합계']
    """
    padding = 40
    line_h = 44
    thumb_size = (120, 120)
    header_h = 120
    row_h = max(thumb_size[1] + 20, line_h * 3)
    table_w = 980
    footer_h = 140
    reason_lines = [s for s in reasons.strip().split("\n")] if reasons.strip() else []
    reason_h = max(100, 28 * max(1, len(reason_lines)))

    # 전체 높이
    h = header_h + 20 + len(items) * row_h + 30 + reason_h + 20 + footer_h + padding * 2
    w = table_w + padding * 2

    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)

    title_font = get_font(46)
    bold_font  = get_font(28)
    text_font  = get_font(24)
    small_font = get_font(22)

    # 헤더 (그림자 있는 큰 제목)
    draw_text_with_shadow(d, (padding, padding), f"미션: {mission_title}", font=title_font,
                          fill=(25,25,25), shadow=(180,180,180), offset=(3,3))

    y = padding + header_h

    # 테이블 헤더
    d.rectangle([(padding-10, y-14), (w-padding+10, y+38)], outline=(225, 225, 225), width=1)
    d.text((padding, y), "구매 내역", font=bold_font, fill=(30, 30, 30))
    y += 56

    # 각 아이템 행
    for _, row in items.iterrows():
        d.rectangle([(padding-10, y-10), (w-padding+10, y+row_h-10)], outline=(238, 238, 238), width=1)
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
    y += 12
    d.text((padding, y), "구매 이유", font=bold_font, fill=(30, 30, 30))
    y += 42
    d.rectangle([(padding-10, y-10), (w-padding+10, y + reason_h)], outline=(225, 225, 225), width=1)
    for i, line in enumerate(reason_lines[:20]):
        d.text((padding, y + i * 28), line, font=small_font, fill=(40, 40, 40))
    y += reason_h + 34

    # 합계/차액
    spent = total
    remain = budget - total
    d.text((padding, y), f"사용한 금액: {format_won(spent)}", font=bold_font, fill=(20, 20, 20))
    d.text((padding + 420, y), f"남은 돈: {format_won(remain)}",
           font=bold_font, fill=(0, 120, 0) if remain >= 0 else (180, 0, 0))

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
# 미션 정의 (+ 대표 이미지)
# -----------------------------
MISSIONS = {
    "카레 만들기": {
        "budget": 15000,
        "img": "https://images.unsplash.com/photo-1604909052604-0e96f2b0f2a3?q=80&w=1200&auto=format&fit=crop"
    },
    "여름캠핑 준비하기": {
        "budget": 30000,
        "img": "https://images.unsplash.com/photo-1502920917128-1aa500764ce7?q=80&w=1200&auto=format&fit=crop"
    },
    "친구 생일파티 준비하기": {
        "budget": 25000,
        "img": "https://images.unsplash.com/photo-1527489342828-043c3f7fbb61?q=80&w=1200&auto=format&fit=crop"
    },
}

# -----------------------------
# HTML 렌더링 헬퍼
# -----------------------------
def product_card_html(name: str, price: int, img_url: str) -> str:
    return f"""
      <div class="card">
        <div class="imgbox"><img src="{img_url}" alt="{name}" /></div>
        <div class="pname">{name}</div>
        <div class="pprice">{format_won(price)}</div>
      </div>
    """

def cart_table_html(rows: pd.DataFrame) -> str:
    trs = []
    for _, r in rows.iterrows():
        trs.append(f"""
          <tr>
            <td><img class="cart-thumb" src="{r['이미지url']}" alt="{r['품명']}" /></td>
            <td>{r['품명']}</td>
            <td>{r['수량']}</td>
            <td>{format_won(r['단가'])}</td>
            <td>{format_won(r['합계'])}</td>
          </tr>
        """)
    return f"""
      <table class="cart-table">
        <thead>
          <tr><th>이미지</th><th>품명</th><th>수량</th><th>단가</th><th>합계</th></tr>
        </thead>
        <tbody>
          {''.join(trs)}
        </tbody>
      </table>
    """

# -----------------------------
# 앱 화면
# -----------------------------
def start_page():
    st.title("🛒 장보기 미션 앱")
    st.subheader("미션을 선택하세요")

    # 미션 카드 3개 (대표 이미지 + 예산)
    cols = st.columns(3)
    for i, (m, meta) in enumerate(MISSIONS.items()):
        with cols[i]:
            st.markdown(
                f"""
                <div class="card">
                  <div class="imgbox" style="height:200px"><img src="{meta['img']}" alt="{m}" /></div>
                  <div class="pname" style="font-size:1.15rem">{m}</div>
                  <div class="pprice">예산: <b>{format_won(meta['budget'])}</b></div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button(f"'{m}' 미션 선택", key=f"select_{i}"):
                st.session_state.mission = m
                st.session_state.budget = meta["budget"]
                st.session_state.cart = {}
                st.session_state.submitted = False
                st.session_state.reasons = ""
                st.session_state.step = "shop"

    st.info("카레 만들기, 여름캠핑, 생일파티 등 상황에 맞는 물건을 골라 보세요!")

def shop_page(df: pd.DataFrame):
    st.title(f"🛍️ 쇼핑 - 미션: {st.session_state.mission}")
    st.caption(f"예산: {format_won(st.session_state.budget)}")

    # 상품 그리드 (HTML로 이미지 렌더링)
    st.markdown('<div class="grid-3">', unsafe_allow_html=True)
    for idx, row in df.reset_index(drop=True).iterrows():
        st.markdown(product_card_html(row["품명"], int(row["가격"]), row["이미지url"]), unsafe_allow_html=True)
        # 각 카드 하단에 수량/버튼 위젯 붙이기
        qcol1, qcol2 = st.columns([2, 1])
        qty = qcol1.number_input("수량", min_value=0, max_value=99, value=0, step=1, key=f"qty_{idx}")
        if qcol2.button("장바구니 담기", key=f"add_{idx}"):
            if int(qty) > 0:
                add_to_cart(row["품명"], int(row["가격"]), row["이미지url"], int(qty))
                st.toast(f"'{row['품명']}' {qty}개를 담았습니다.", icon="🧺")
            else:
                st.toast("수량을 1 이상 선택하세요.", icon="⚠️")
    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # 장바구니 (이미지 포함 HTML 테이블)
    st.subheader("🧺 장바구니")
    cart = st.session_state.cart
    if not cart:
        st.write("아직 담은 물건이 없어요.")
    else:
        cart_df = pd.DataFrame(
            [
                {"품명": k, "수량": v["qty"], "단가": v["price"], "합계": v["price"] * v["qty"], "이미지url": v["img_url"]}
                for k, v in cart.items()
            ]
        )
        st.markdown(cart_table_html(cart_df), unsafe_allow_html=True)

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

    # 제출하기 → 결과 페이지 이동
    submitted = st.button("제출하기", type="primary", disabled=over_budget or (total <= 0))
    if submitted:
        st.session_state.submitted = True
        st.session_state.step = "result"
        st.rerun()

def result_page():
    st.title(f"✅ 결과 - 미션: {st.session_state.mission}")

    # 안전장치
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

    # PNG 생성 품질을 위해 미리 이미지 로드 (UI는 HTML로)
    df_items["이미지"] = df_items["이미지url"].apply(lambda u: fetch_image(u, size=(120, 120)))

    st.subheader("🧾 구매한 물건")
    # 구매 목록을 카드 그리드로 표시 (HTML 이미지)
    st.markdown('<div class="grid-3">', unsafe_allow_html=True)
    for _, row in df_items.iterrows():
        st.markdown(product_card_html(row["품명"], int(row["단가"]), row["이미지url"]), unsafe_allow_html=True)
        st.markdown(f"수량: {row['수량']} | 단가: {format_won(row['단가'])} | 합계: {format_won(row['합계'])}")
    st.markdown("</div>", unsafe_allow_html=True)

    total = int(df_items["합계"].sum())
    remain = st.session_state.budget - total

    col1, col2 = st.columns(2)
    with col1:
        st.metric("사용한 금액", format_won(total))
    with col2:
        st.metric("남은 돈(차액)", format_won(remain), delta=None)

    st.markdown("### ✍️ 구매 이유")
    st.session_state.reasons = st.text_area(
        "왜 이 물건들을 골랐나요?",
        value=st.session_state.reasons,
        placeholder="예: 카레 재료를 빠짐없이 사기 위해서, 캠핑에 필요한 기본 장비를 갖추기 위해서 등",
        height=140
    )

    if st.session_state.reasons.strip():
        if st.button("PNG로 다운로드", type="primary"):
            png_bytes = make_result_image(
                mission_title=st.session_state.mission,
                reasons=st.session_state.reasons,
                items=df_items,
                total=total,
                budget=st.session_state.budget
            )
            st.download_button(
                "PNG로 다운로드",
                data=png_bytes,
                file_name=f"{st.session_state.mission}_결과.png",
                mime="image/png",
                type="primary"
            )
            st.success("이미지를 생성했어요! 상단의 다운로드 버튼을 눌러 저장하세요.")
    else:
        st.info("구매 이유를 모두 작성하면 ‘PNG로 다운로드’ 버튼이 나타납니다.")

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
