import io
import math
from typing import Dict, Any
import requests
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="장보기 미션 앱", page_icon="🛒", layout="wide")


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
    # 필수 컬럼 존재 여부 체크
    for needed in ["품명", "가격", "이미지url"]:
        if needed not in df.columns:
            raise ValueError("products.csv에는 '품명, 가격, 이미지url' 열이 반드시 있어야 합니다.")
    # 가격 숫자화
    def to_price(v):
        if pd.isna(v):
            return 0
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).replace(",", "").replace("원", "").strip()
        try:
            return int(float(s))
        except Exception:
            return 0
    df["가격"] = df["가격"].apply(to_price)
    return df[["품명", "가격", "이미지url"]]


@st.cache_data(show_spinner=False)
def fetch_image(url: str, size=(120, 120)) -> Image.Image:
    """URL에서 이미지를 가져와 썸네일 생성. 실패 시 플레이스홀더."""
    try:
        r = requests.get(url, timeout=7)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        # 간단 플레이스홀더
        img = Image.new("RGBA", size, (230, 230, 230, 255))
        d = ImageDraw.Draw(img)
        d.text((10, size[1]//2 - 8), "이미지\n없음", fill=(100, 100, 100))
        return img
    img.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255, 0))
    canvas.paste(img, ((size[0]-img.width)//2, (size[1]-img.height)//2))
    return canvas


def get_font(prefer_size=32):
    """
    한글이 깨지지 않도록 대표 한글 글꼴 후보를 순차적으로 탐색.
    프로젝트 루트에 fonts/NotoSansCJK-Regular.otf 등을 두면 가장 먼저 시도합니다.
    """
    candidates = [
        "fonts/NotoSansCJK-Regular.otf",
        "fonts/NotoSansKR-Regular.otf",
        "fonts/NanumGothic.ttf",        # Linux, macOS에 흔함
        "/System/Library/Fonts/AppleGothic.ttf",  # macOS
        "C:/Windows/Fonts/malgun.ttf",  # Windows
        "C:/Windows/Fonts/NanumGothic.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, prefer_size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_result_image(mission_title: str, reasons: str, items: pd.DataFrame, total: int, budget: int) -> bytes:
    """
    결과 이미지를 PIL로 생성하여 PNG 바이트로 반환.
    items: 컬럼 ['이미지', '품명', '수량', '단가', '합계']
    """
    # 레이아웃 설정
    padding = 40
    line_h = 44
    thumb_size = (120, 120)
    header_h = 100
    row_h = max(thumb_size[1] + 20, line_h * 3)
    table_w = 900
    footer_h = 120
    reason_lines = [s for s in reasons.strip().split("\n")] if reasons.strip() else []
    reason_h = max(80, 24 * max(1, len(reason_lines)))

    # 전체 높이 계산
    h = header_h + 20 + len(items) * row_h + 30 + reason_h + 20 + footer_h + padding * 2
    w = table_w + padding * 2

    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)

    title_font = get_font(40)
    bold_font = get_font(28)
    text_font = get_font(24)
    small_font = get_font(20)

    # 헤더
    d.text((padding, padding), f"미션: {mission_title}", font=title_font, fill=(20, 20, 20))

    y = padding + header_h

    # 테이블 헤더
    d.rectangle([(padding-10, y-10), (w-padding+10, y+40)], outline=(220, 220, 220), width=1)
    d.text((padding, y), "구매 내역", font=bold_font, fill=(30, 30, 30))
    y += 60

    # 각 아이템 행
    for _, row in items.iterrows():
        # 카드 테두리
        d.rectangle([(padding-10, y-10), (w-padding+10, y+row_h-10)], outline=(235, 235, 235), width=1)

        # 썸네일
        try:
            thumb = row["이미지"]
            if not isinstance(thumb, Image.Image):
                thumb = fetch_image(row["이미지url"], size=thumb_size)
        except Exception:
            thumb = fetch_image("", size=thumb_size)
        img.paste(thumb.convert("RGBA"), (padding, y), mask=thumb)

        # 텍스트
        x_text = padding + thumb_size[0] + 20
        d.text((x_text, y + 4), f"{row['품명']}", font=bold_font, fill=(20, 20, 20))
        d.text((x_text, y + 4 + line_h), f"수량: {row['수량']}   단가: {format_won(row['단가'])}", font=text_font, fill=(60, 60, 60))
        d.text((x_text, y + 4 + line_h*2), f"합계: {format_won(row['합계'])}", font=text_font, fill=(0, 0, 0))

        y += row_h

    # 구매 이유
    y += 10
    d.text((padding, y), "구매 이유", font=bold_font, fill=(30, 30, 30))
    y += 40
    box_top = y - 10
    d.rectangle([(padding-10, box_top), (w-padding+10, y + reason_h)], outline=(220, 220, 220), width=1)
    for i, line in enumerate(reason_lines[:15]):  # 과도하게 길면 일부만
        d.text((padding, y + i * 24), line, font=small_font, fill=(40, 40, 40))
    y += reason_h + 30

    # 합계/차액
    spent = total
    remain = budget - total
    d.text((padding, y), f"사용한 금액: {format_won(spent)}", font=bold_font, fill=(20, 20, 20))
    d.text((padding + 350, y), f"남은 돈: {format_won(remain)}", font=bold_font, fill=(0, 120, 0) if remain >= 0 else (180, 0, 0))

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
# 미션 정의
# -----------------------------
MISSIONS = {
    "카레 만들기": 15000,
    "여름캠핑 준비하기": 30000,
    "친구 생일파티 준비하기": 25000,
}


# -----------------------------
# 앱 실행
# -----------------------------
def start_page():
    st.title("🛒 장보기 미션 앱")
    st.subheader("미션을 선택하세요")

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


def shop_page(df: pd.DataFrame):
    st.title(f"🛍️ 쇼핑 - 미션: {st.session_state.mission}")
    st.caption(f"예산: {format_won(st.session_state.budget)}")

    # 상품 그리드
    n_cols = 3
    rows = math.ceil(len(df) / n_cols)

    for r in range(rows):
        cols = st.columns(n_cols)
        for c in range(n_cols):
            idx = r * n_cols + c
            if idx >= len(df):
                continue
            row = df.iloc[idx]
            with cols[c]:
                with st.container(border=True):
                    st.image(fetch_image(row["이미지url"]), use_column_width=True)
                    st.markdown(f"**{row['품명']}**")
                    st.markdown(f"{format_won(row['가격'])}")
                    qty_col, plus_col = st.columns([2, 1])
                    qty = qty_col.number_input("수량", min_value=0, max_value=99, value=0, step=1, key=f"qty_{idx}")
                    if plus_col.button("장바구니 담기", key=f"add_{idx}"):
                        add_to_cart(row["품명"], int(row["가격"]), row["이미지url"], int(qty))
                        st.toast(f"'{row['품명']}' {qty}개를 담았습니다.", icon="🧺")

    st.divider()

    # 장바구니 요약 (페이지 하단)
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
        cart_df_display = cart_df[["품명", "수량", "단가", "합계"]].copy()
        cart_df_display["단가"] = cart_df_display["단가"].apply(format_won)
        cart_df_display["합계"] = cart_df_display["합계"].apply(format_won)
        st.dataframe(cart_df_display, use_container_width=True, hide_index=True)

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

    # 제출하기 버튼 (예산 초과 시 비활성화)
    submitted = st.button("제출하기", type="primary", disabled=over_budget or (total <= 0))
    if submitted:
        st.session_state.submitted = True
        st.session_state.step = "result"
        st.rerun()


def result_page():
    st.title(f"✅ 결과 - 미션: {st.session_state.mission}")

    # 안전장치: 제출하지 않고 직접 접근한 경우
    if not st.session_state.submitted:
        st.warning("제출 버튼을 누른 경우에만 결과 화면으로 이동할 수 있어요.")
        if st.button("쇼핑 화면으로 돌아가기"):
            st.session_state.step = "shop" if st.session_state.mission else "start"
            st.rerun()
        return

    # 장바구니 표
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
    # 이미지 미리 불러오기(다운로드 이미지 품질 안정)
    df_items["이미지"] = df_items["이미지url"].apply(lambda u: fetch_image(u, size=(120, 120)))

    # 화면 표시용 표
    show_df = df_items[["품명", "수량", "단가", "합계"]].copy()
    show_df["단가"] = show_df["단가"].apply(format_won)
    show_df["합계"] = show_df["합계"].apply(format_won)

    # 그리드로 이미지 + 정보 표시
    st.subheader("🧾 구매한 물건")
    n_cols = 3
    rows = math.ceil(len(df_items)/n_cols)
    for r in range(rows):
        cols = st.columns(n_cols)
        for c in range(n_cols):
            idx = r*n_cols + c
            if idx >= len(df_items):
                continue
            row = df_items.iloc[idx]
            with cols[c]:
                with st.container(border=True):
                    st.image(row["이미지"], use_column_width=True)
                    st.markdown(f"**{row['품명']}**")
                    st.markdown(f"수량: {row['수량']} | 단가: {format_won(row['단가'])} | 합계: {format_won(row['합계'])}")

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
        # 그림으로 저장 버튼 노출
        if st.button("🖼️ 그림으로 저장"):
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
        st.info("구매 이유를 모두 작성하면 '그림으로 저장' 버튼이 나타납니다.")

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

    # 단계별 화면 전환 (제출한 경우에만 result 진입)
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

