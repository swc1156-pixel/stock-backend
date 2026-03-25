import json
import re
import random
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import concurrent.futures
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from typing import List, Optional

import os
from dotenv import load_dotenv
import requests
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from googletrans import Translator
    translator = Translator()
except ImportError:
    translator = None

load_dotenv()  # .env 파일에서 환경 변수를 불러옵니다.

try:
    # 1. 신형 라이브러리 우선 시도
    from google import genai
    from google.genai import types
    GEMINI_API_KEY = "AIzaSyB8hmvlHWRX5Pa1Tn9rd7n5-hIOhQUDuws"
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    ai_legacy = False
except ImportError:
    # 2. 신형이 없으면 예전에 설치해둔 구형 라이브러리로 자동 전환하여 에러 방지
    try:
        import google.generativeai as genai
        GEMINI_API_KEY = "AIzaSyB8hmvlHWRX5Pa1Tn9rd7n5-hIOhQUDuws"
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            ai_client = genai.GenerativeModel("gemini-2.5-flash")
        else:
            ai_client = None
        ai_legacy = True
    except ImportError:
        ai_client = None
        ai_legacy = False

# (삭제됨) 최신 yfinance는 내부적으로 curl_cffi를 사용하여 봇 차단을 자체 우회하므로,
# 일반 requests.Session()을 전달하면 오히려 에러(YFDataException)가 발생합니다.


SECTOR_TRANSLATIONS = {
    "Technology": "정보기술",
    "Healthcare": "헬스케어",
    "Financial Services": "금융",
    "Consumer Cyclical": "임의소비재",
    "Consumer Defensive": "필수소비재",
    "Energy": "에너지",
    "Industrials": "산업재",
    "Basic Materials": "소재",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
    "Communication Services": "통신 서비스",
    "ETF": "상장지수펀드(ETF)",
    "EQUITY": "주식",
}

COMPANY_TRANSLATIONS = {
    "AAPL": "애플",
    "MSFT": "마이크로소프트",
    "GOOG": "알파벳 (구글)",
    "GOOGL": "알파벳 (구글)",
    "AMZN": "아마존",
    "META": "메타 플랫폼스",
    "TSLA": "테슬라",
    "NVDA": "엔비디아",
    "NFLX": "넷플릭스",
    "AMD": "AMD",
    "INTC": "인텔",
    "QCOM": "퀄컴",
    "TSM": "TSMC", "AVGO": "브로드컴", "ASML": "ASML", "CRM": "세일즈포스",
    "ORCL": "오라클", "ADBE": "어도비", "CSCO": "시스코", "TXN": "텍사스 인스트루먼트",
    "IBM": "IBM", "NOW": "스노우플레이크", "PLTR": "팔란티어", "ARM": "ARM",
    "SMCI": "슈퍼마이크로", "UBER": "우버", "ABNB": "에어비앤비", "PYPL": "페이팔",
    "SQ": "블록 (스퀘어)", "HOOD": "로빈후드",
    "JPM": "JP모건", "V": "비자", "MA": "마스터카드", "BAC": "뱅크오브아메리카",
    "WMT": "월마트", "PG": "프록터앤갬블", "KO": "코카콜라", "PEP": "펩시코",
    "COST": "코스트코", "MCD": "맥도날드", "DIS": "디즈니", "NKE": "나이키",
    "SBUX": "스타벅스", "JNJ": "존슨앤존슨", "LLY": "일라이릴리", "UNH": "유나이티드헬스",
    "MRK": "머크", "ABBV": "애브비", "PFE": "화이자", "XOM": "엑슨모빌", "CVX": "쉐브론",
    "O": "리얼티 인컴", "SCHW": "찰스 슈왑", "BA": "보잉", "GE": "제너럴 일렉트릭",
    "SPY": "SPDR S&P 500 ETF", "IVV": "iShares Core S&P 500 ETF", "VOO": "Vanguard S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust", "TQQQ": "ProShares UltraPro QQQ", "SOXX": "iShares Semiconductor ETF",
    "SOXL": "Direxion Daily Semiconductor Bull 3X", "SCHD": "Schwab US Dividend Equity ETF",
    "ARKK": "ARK Innovation ETF", "TLT": "iShares 20+ Year Treasury Bond ETF",
    "TMF": "Direxion Daily 20+ Year Treasury Bull 3X",
    "005930.KS": "삼성전자", "000660.KS": "SK하이닉스", "373220.KS": "LG에너지솔루션",
    "207940.KS": "삼성바이오로직스", "005380.KS": "현대차", "000270.KS": "기아",
    "068270.KS": "셀트리온", "035420.KS": "NAVER", "035720.KS": "카카오",
    "051910.KS": "LG화학", "006400.KS": "삼성SDI", "028260.KS": "삼성물산",
    "005490.KS": "POSCO홀딩스", "105560.KS": "KB금융", "055550.KS": "신한지주",
    "032830.KS": "삼성생명", "012330.KS": "현대모비스", "034730.KS": "SK",
    "033780.KS": "KT&G", "003550.KS": "LG", "034020.KS": "두산에너빌리티",
    "010140.KS": "삼성중공업", "011200.KS": "HMM", "323410.KS": "카카오뱅크",
    "316140.KS": "우리금융지주", "015760.KS": "한국전력", "032640.KS": "LG유플러스",
    "018260.KS": "삼성SDS", "259960.KS": "크래프톤", "011170.KS": "롯데케미칼",
    "096770.KS": "SK이노베이션", "010950.KS": "S-Oil", "036570.KS": "엔씨소프트",
    "090430.KS": "아모레퍼시픽", "009150.KS": "삼성전기", "004020.KS": "현대제철",
    "017670.KS": "SK텔레콤", "352820.KS": "하이브", "241560.KS": "두산밥캣",
    "010130.KS": "고려아연", "042700.KS": "한미반도체", "024110.KS": "기업은행",
    "086520.KQ": "에코프로", "247540.KQ": "에코프로비엠", "066970.KQ": "엘앤에프",
    "022100.KS": "포스코DX", "028300.KQ": "HLB", "196170.KQ": "알테오젠",
    "041510.KQ": "에스엠", "058470.KQ": "리노공업", "035900.KQ": "JYP Ent.",
    "293490.KQ": "카카오게임즈", "214150.KQ": "클래시스", "278280.KQ": "천보",
}

app = FastAPI(title="Stock Dashboard Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인(Vercel 포함)에서의 접속을 허용합니다.
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST 등 모든 통신 방식 허용
    allow_headers=["*"],  # 모든 헤더 허용
)


class Financials(BaseModel):
    revenue: str
    operatingIncome: str
    eps: str
    per: str
    pbr: str
    roe: str

class AIAnalysisResponse(BaseModel):
    result: str


class NewsItem(BaseModel):
    title: str
    publisher: str
    link: str
    publishTime: int


class QuoteResponse(BaseModel):
    symbol: str
    name: str
    sector: str
    exchange: Optional[str] = None
    price: Optional[float]
    priceKrw: Optional[float] = None
    change: Optional[float]
    changePct: Optional[float]
    high52w: Optional[float]
    currency: str
    financials: Financials
    earningsDate: Optional[str] = None
    institutionHoldPct: Optional[str] = None
    businessSummary: Optional[str] = None
    news: List[NewsItem] = []


class ChartPoint(BaseModel):
    date: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]


class ChartResponse(BaseModel):
    symbol: str
    interval: str
    data: List[ChartPoint]


class SearchResult(BaseModel):
    symbol: str
    shortname: str
    longname: str
    exchange: str


class SearchResponse(BaseModel):
    results: List[SearchResult]

class InvestorTrend(BaseModel):
    date: str
    retail: float
    foreigner: float
    institution: float
    priceChange: float

@app.get("/api/ai-analysis/{symbol}", response_model=AIAnalysisResponse)
def get_ai_analysis(symbol: str, mode: int = 1):
    if not ai_client:
        raise HTTPException(status_code=500, detail="AI 라이브러리가 설치되지 않았습니다. 백엔드 터미널에서 'pip install google-generativeai' 를 입력해주세요.")
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        name = info.get("longName") or info.get("shortName") or symbol
        
        if mode == 1:
            hist = ticker.history(period="1mo")
            if not hist.empty:
                prices = [round(x, 2) for x in hist["Close"].tolist()]
                prompt = f"[{name} ({symbol}) 기술적 차트 패턴 분석]\n최근 한 달간의 종가 흐름: {prices}\n이 데이터를 바탕으로 현재 차트의 지지선과 저항선을 유추하고, 형성되고 있는 패턴(예: 쌍바닥, 깃발형 수렴, 헤드앤숄더 등)이 있는지 프로 트레이더의 시각에서 전문적이고 간결하게 분석해줘."
            else:
                prompt = f"[{name} ({symbol})]의 전반적인 기술적 변동성 특징과 차트 성향을 설명해줘."
        elif mode == 2:
            prompt = f"[{name} ({symbol}) 실적 및 모멘텀 분석]\n이 기업의 최근 시장 내 핵심 이슈와 다음 실적 발표에서 기대되거나 우려되는 부분(가이던스, 매크로 영향 등)을 펀드매니저의 시선에서 딱 3줄로 명확하게 요약해줘."
        elif mode == 3:
            pe = info.get("trailingPE", "N/A")
            pbr = info.get("priceToBook", "N/A")
            roe = info.get("returnOnEquity", "N/A")
            prompt = f"[{name} ({symbol}) 대가의 투자 의견]\n이 기업의 현재 지표 -> PER: {pe}, PBR: {pbr}, ROE: {roe}.\n이 비즈니스 모델과 지표를 보고, '워런 버핏(가치투자)'과 '피터 린치(성장투자)'의 페르소나에 완벽하게 빙의해서 각각 이 주식에 대해 어떤 평가를 내릴지 대화체로 작성해줘. 날카로운 독설과 칭찬을 가감 없이 섞어줘."
        elif mode == 4:
            prompt = f"""
[지침 0] 핵심 정체성 및 언어 헌법
▶ ROLE: 30년 경력의 월드클래스 투자 분석가이자 포렌식 감사관.
▶ TONE: 건조함, 냉소적, 전문가적 단정형 문체. 핵심 데이터는 Bold 처리.
▶ LANGUAGE ENFORCEMENT: 무조건 100% 한국어 출력. 전문 용어는 쉬운 설명 병기. 애매한 표현 금지. 표/이미지 사용 금지.

[Trigger Input]: {name} ({symbol})
위 종목에 대해 다음 양식(TRINITY LAYER 1)을 엄격히 준수하여 1차 데이터 시트를 작성하라. 인터넷 검색 도구를 적극 활용하여 최신 데이터를 반영하라.

① [MACRO & MARKET 3-POINT CHECK] (미국 기준금리, DXY, VIX, F&G 등)
② [IDENTITY & FUNDAMENTALS] (섹터, 흑자/적자, 시총, 배당, 현금보유, 현금소진율 등)
③ [POLITICAL & REGULATORY RADAR] (규제 환경, 정책 지원, 로비 등)
④ [OMNI-CHANNEL DILUTION DRAGNET] (유상증자, CB, 락업 등 잠재적 주가 희석 요인 전수 조사)
⑤ [OMNI-ENTITY FORENSICS] (전략적 투자자, 내부자 거래, 기관 수급)
⑥ [HIDDEN RISK RADAR] (공급망/IP 병목, 대차/공매도, 법적 리스크)
⑦ [ANALYST VERDICT] (1차 결론, 데이터 신뢰도 평가, 핵심 주의사항 1줄 요약)

*마지막에 "데이터 수집 및 검증이 완료되었습니다. '⚖️ 2차 정밀 추론 (가치 평가)' 버튼을 눌러 정밀 분석을 시작하세요."라는 안내 문구를 반드시 포함할 것.*
"""
        elif mode == 5:
            prompt = f"""
[지침 0] 핵심 정체성 및 언어 헌법
▶ ROLE: 30년 경력의 월드클래스 투자 분석가이자 포렌식 감사관.
▶ TONE: 건조함, 냉소적, 전문가적 단정형 문체. 핵심 데이터는 Bold 처리.
▶ LANGUAGE ENFORCEMENT: 무조건 100% 한국어 출력. 전문 용어는 쉬운 설명 병기. 애매한 표현 금지. 표/이미지 사용 금지. 선형적 외삽(단순한 미래 낙관) 금지.

[Trigger Input]: {name} ({symbol}) 추론 시작
명령이 하달되었다. 위 종목에 대해 다음 양식(THE VALUATION MASTER)을 엄격히 준수하여 정밀 분석 보고서를 작성하라. 요약을 금지하고 모든 모듈을 강제로 순차 출력하라.

1. EXECUTIVE SUMMARY DASHBOARD (매크로 민감도, 종합 판정 점수 10점 만점, 포렌식 위험도)
2. INDEX ELIGIBILITY AUDIT (시가총액/유동성 등 정량적/정성적 심사 및 지수 편입 적격 판정)
3. BUSINESS MODEL LOGIC (자본->핵심자산->제품->매출->고객 도식화 및 비즈니스 병목 구간 분석)
4. SCENARIO MATRIX (상승/기본/하락 시나리오 확률 및 꼬리 위험 - 천국 시 주가/지옥 시 주가)
5. VALUATION & "PRICED-IN" LOGIC (내재 가치, 상대 가치 비교, 현재 주가 선반영률)
6. FORENSIC DEEP-DIVE (희석 독성 점수 및 감점 사유, 이익의 질 평가)
7. SECTOR SPECIFIC DEEP-MESH (해당 업종 특화 핵심 리스크 및 경쟁 우위 팩트체크)
8. PARTNERSHIP & INSIDER (내부자 심리 지수, 전략적 의도, 기관 매도 이유 역설계 - Devil's Advocate)
9. FINAL VERDICT (진입가/목표가/손절가 구간 및 분석가의 냉혹한 최종 조언)
"""
        else:
            prompt = "잘못된 요청입니다."
            
        if ai_legacy:
            resp = ai_client.generate_content(
                prompt, 
                tools="google_search_retrieval",
                safety_settings={
                    'HARASSMENT': 'BLOCK_ONLY_HIGH',
                    'HATE': 'BLOCK_ONLY_HIGH',
                    'SEXUAL': 'BLOCK_ONLY_HIGH',
                    'DANGEROUS': 'BLOCK_ONLY_HIGH'
                }
            )
        else:
            resp = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    safety_settings=[
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                    ]
                )
            )
            
        try:
            result_text = resp.text
        except Exception:
            result_text = None
            
        if not result_text:
            result_text = "⚠️ AI가 응답을 생성하지 못했습니다. (프롬프트 내의 강한 단어들이 Google 안전 필터에 의해 차단되었거나, 검색 결과를 가져오지 못했을 수 있습니다.)"
            
        return AIAnalysisResponse(result=result_text)
    except Exception as e:
        print(f"AI Error: {e}")
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            raise HTTPException(status_code=429, detail="⚠️ 제미나이(Gemini) API의 무료 호출 한도(1분에 15회)를 초과했습니다.\n잠시 후(약 1분 뒤) 다시 시도해주세요.")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai-recommend", response_model=AIAnalysisResponse)
def get_ai_recommend(market: str = "NASDAQ"):
    import pandas as pd
    if not ai_client:
        raise HTTPException(status_code=500, detail="AI 라이브러리가 설치되지 않았습니다.")
    
    symbols_map = {}
    if market == "KOSPI":
        symbols_map = {"005930.KS": "삼성전자", "000660.KS": "SK하이닉스", "373220.KS": "LG에너지솔루션", "207940.KS": "삼성바이오로직스", "005380.KS": "현대차", "000270.KS": "기아", "105560.KS": "KB금융", "035420.KS": "NAVER", "035720.KS": "카카오", "068270.KS": "셀트리온", "005490.KS": "POSCO홀딩스", "051910.KS": "LG화학"}
    elif market == "KOSDAQ":
        symbols_map = {"086520.KQ": "에코프로", "247540.KQ": "에코프로비엠", "196170.KQ": "알테오젠", "028300.KQ": "HLB", "066970.KQ": "엘앤에프", "041510.KQ": "에스엠", "035900.KQ": "JYP Ent.", "293490.KQ": "카카오게임즈", "058470.KQ": "리노공업", "214150.KQ": "클래시스", "278280.KQ": "천보", "022100.KS": "포스코DX"}
    elif market == "NASDAQ":
        symbols_map = {"AAPL": "애플", "MSFT": "마이크로소프트", "GOOGL": "알파벳", "AMZN": "아마존", "META": "메타", "TSLA": "테슬라", "NVDA": "엔비디아", "NFLX": "넷플릭스", "AMD": "AMD", "AVGO": "브로드컴", "QCOM": "퀄컴", "INTC": "인텔"}
    elif market == "SP500":
        symbols_map = {"JPM": "JP모건", "UNH": "유나이티드헬스", "V": "비자", "MA": "마스터카드", "HD": "홈디포", "PG": "프록터앤갬블", "CVX": "쉐브론", "MRK": "머크", "ABBV": "애브비", "PEP": "펩시코", "KO": "코카콜라", "BAC": "뱅크오브아메리카"}
    else:
        symbols_map = {"AAPL": "애플", "NVDA": "엔비디아"}

    data_context = ""
    try:
        for sym, name in symbols_map.items():
            try:
                tk = yf.Ticker(sym)
                hist = tk.history(period="1mo")
                if not hist.empty and "Close" in hist.columns:
                    prices = hist["Close"].dropna().tail(20).tolist()
                    prices = [round(float(x), 2) for x in prices]
                    if prices:
                        data_context += f"- {name} ({sym}): {prices}\n"
            except Exception:
                continue
    except Exception as e:
        print(f"Download Error: {e}")

    if not data_context:
        raise HTTPException(status_code=500, detail="데이터 수집에 실패했습니다.")

    prompt = f"""
[지침 0] 핵심 정체성 및 언어 헌법
▶ ROLE: 30년 경력의 월드클래스 기술적 투자 분석가 및 스윙 트레이더.
▶ TONE: 단호하고 날카로운 전문가적 문체. 상승/하락에 대한 근거를 명확히 제시할 것.
▶ LANGUAGE ENFORCEMENT: 무조건 100% 한국어.

[Trigger Input]: {market} 대표 종목들의 최근 약 한 달간(20거래일) 종가(Close) 흐름 데이터가 주어졌다. 이 가격 배열을 머릿속으로 시각화하여 차트 패턴(쌍바닥, 수렴 돌파, 눌림목, V자 반등 등)을 유추하고, 차트 매매 기법 관점에서 **현재 시점에서 가장 매수하기 매력적인 TOP 3 종목**을 선정하라.

[데이터]
{data_context}

[출력 양식]
📈 {market} AI 차트 매매 스캐너 결과
==================================

🏆 TOP 1 추천: [종목명]
- 차트 패턴 및 선정 사유: (가격 흐름 데이터를 기반으로 차트 분석 논리 서술)
- 매매 전략: 진입가, 목표가, 손절가

🥈 TOP 2 추천: [종목명]
- 차트 패턴 및 선정 사유:
- 매매 전략: 진입가, 목표가, 손절가

🥉 TOP 3 추천: [종목명]
- 차트 패턴 및 선정 사유:
- 매매 전략: 진입가, 목표가, 손절가

⚠️ [트레이더의 경고]
- (현재 시장 변동성이 크므로 비중 조절 필수 등 짧은 조언)
"""
    try:
        if ai_legacy:
            resp = ai_client.generate_content(
                prompt,
                safety_settings={
                    'HARASSMENT': 'BLOCK_ONLY_HIGH',
                    'HATE': 'BLOCK_ONLY_HIGH',
                    'SEXUAL': 'BLOCK_ONLY_HIGH',
                    'DANGEROUS': 'BLOCK_ONLY_HIGH'
                }
            )
        else:
            resp = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    safety_settings=[
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                    ]
                )
            )
            
        try:
            result_text = resp.text
        except Exception:
            result_text = None
            
        return AIAnalysisResponse(result=result_text if result_text else "⚠️ AI가 응답을 생성하지 못했습니다. (안전 필터에 의해 차단되었을 수 있습니다.)")
    except Exception as e:
        print(f"AI Recommend Error: {e}")
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            raise HTTPException(status_code=429, detail="⚠️ 제미나이(Gemini) API의 무료 호출 한도(1분에 15회)를 초과했습니다.\n잠시 후(약 1분 뒤) 다시 시도해주세요.")
        raise HTTPException(status_code=500, detail=str(e))

def _safe_number(v, default=None) -> Optional[float]:
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default


_exchange_rate_cache = {"rate": 1350.0, "time": datetime.min}

def get_korean_name_from_naver(symbol: str) -> Optional[str]:
    clean_sym = symbol.split('.')[0]
    
    # KOSPI/KOSDAQ 코드는 숫자로만 이루어져 있으므로, 알파벳(해외주식)인 경우 즉시 종료합니다.
    if not clean_sym.isdigit():
        return None
        
    try:
        # 1차 시도: 빠르고 안정적인 모바일 네이버 증권 통합 정보 API
        url = f"https://m.stock.naver.com/api/stock/{clean_sym}/integration"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode('utf-8'))
            name = data.get("stockName")
            if name:
                return name
    except Exception:
        pass
        
    try:
        # 2차 시도: 기존 자동완성 API 백업
        safe_query = urllib.parse.quote(clean_sym)
        naver_url = f"https://ac.finance.naver.com/ac?q={safe_query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        req = urllib.request.Request(naver_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode('utf-8'))
            items = data.get("items", [[]])[0]
            for item in items:
                if len(item) >= 2:
                    naver_ticker = item[1].upper().replace('.', '-').replace(' ', '')
                    search_ticker = clean_sym.upper().replace('.', '-').replace(' ', '')
                    if naver_ticker == search_ticker:
                        return item[0]
    except Exception:
        pass
    return None

_us_stock_name_cache = {}
_company_name_translate_cache = {}
_business_summary_cache = {}

def translate_company_name_to_ko(name_eng: str) -> str:
    if name_eng in _company_name_translate_cache:
        return _company_name_translate_cache[name_eng]
        
    is_translated = False
    ko_name = name_eng
    if translator:
        try:
            res = translator.translate(name_eng, dest='ko').text
            if res and res != name_eng:
                ko_name = res
                is_translated = True
        except Exception:
            pass
            
    # (API 무료 할당량 초과 에러 429 방지를 위해 백그라운드 AI 번역 기능은 비활성화합니다)
    # 프론트엔드에서 여러 종목을 동시에 띄울 때 AI 요청이 폭주하여 한도가 초과되는 것을 막습니다.
            
    _company_name_translate_cache[name_eng] = ko_name
    return ko_name

def resolve_stock_name(sym: str, name_eng: str) -> tuple:
    if sym in COMPANY_TRANSLATIONS:
        return sym, COMPANY_TRANSLATIONS[sym]
    if sym in _us_stock_name_cache:
        return sym, _us_stock_name_cache[sym]
    
    ko_name = get_korean_name_from_naver(sym)
    if not ko_name:
        ko_name = translate_company_name_to_ko(name_eng)

    final_name = ko_name
    _us_stock_name_cache[sym] = final_name
    return sym, final_name

def get_usd_to_krw():
    now = datetime.now()
    # 환율 정보는 1시간(3600초)마다 한 번씩만 갱신하여 속도 저하를 방지합니다.
    if (now - _exchange_rate_cache["time"]).total_seconds() > 3600:
        try:
            tk = yf.Ticker("KRW=X")
            hist = tk.history(period="1d")
            if not hist.empty:
                rate = hist["Close"].iloc[-1]
                _exchange_rate_cache["rate"] = float(rate)
                _exchange_rate_cache["time"] = now
        except Exception as e:
            print(f"Exchange rate error: {e}")
    return _exchange_rate_cache["rate"]


@app.get("/")
def home():
    # 1. 메인 주소 확인용 (https://...onrender.com/ 접속 시 확인)
    return {"status": "alive", "message": "Stock API is running"}


@app.get("/api/search/{query}", response_model=SearchResponse)
def search_symbols(query: str):
    try:
        results = []

        # 1. 네이버 금융 자동완성 API 연동 (모든 코스피/코스닥 종목 100% 지원)
        try:
            safe_query = urllib.parse.quote(query)
            naver_url = f"https://ac.finance.naver.com/ac?q={safe_query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
            naver_req = urllib.request.Request(naver_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(naver_req, timeout=3) as response:
                data = json.loads(response.read().decode('utf-8'))
                items = data.get("items", [[]])[0]
                for item in items:
                    if len(item) >= 3:
                        name = item[0]
                        code = item[1]
                        market = item[2]
                        
                        # 야후 파이낸스 규격으로 변환
                        if market == "KOSPI":
                            symbol = f"{code}.KS"
                        elif market == "KOSDAQ":
                            symbol = f"{code}.KQ"
                        else:
                            continue
                        
                        # 검색된 한글 이름을 캐시에 미리 저장하여, 리스트 추가 시 즉시 재사용
                        _us_stock_name_cache[symbol] = name
                        results.append(
                            SearchResult(
                                symbol=symbol,
                                shortname=name,
                                longname=name,
                                exchange=market
                            )
                        )
        except Exception as e:
            print(f"Naver Search Error: {e}")

        # 2. 로컬 번역 사전(COMPANY_TRANSLATIONS)을 활용한 즉각적인 부분 일치 검색
        query_no_space = query.replace(" ", "").lower()
        if query_no_space:
            for sym, name in COMPANY_TRANSLATIONS.items():
                # 검색어가 영어 심볼이나 한글 이름에 포함되어 있으면 결과에 즉시 추가
                if query_no_space in sym.lower() or query_no_space in name.replace(" ", "").lower():
                    if not any(r.symbol == sym for r in results):
                        results.append(
                            SearchResult(
                                symbol=sym,
                                shortname=name,
                                longname=name,
                                exchange="KOR" if sym.endswith((".KS", ".KQ")) else "US"
                            )
                        )

        # 3. 야후 파이낸스 검색 (해외 주식 및 기존 로직 유지)
        try:
            search_q = query
            query_clean = query.replace(" ", "")
            ko_to_en = {v.replace(" ", ""): k for k, v in COMPANY_TRANSLATIONS.items()}
            
            if query_clean in ko_to_en:
                search_q = ko_to_en[query_clean]
            else:
                for ko_name, en_ticker in ko_to_en.items():
                    if query_clean in ko_name:
                        search_q = en_ticker
                        break
                else:
                    if translator and re.search(r'[가-힣]', query):
                        try:
                            res = translator.translate(query, dest='en').text
                            if res:
                                search_q = res
                        except Exception:
                            pass

            safe_query = urllib.parse.quote(search_q)
            yahoo_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={safe_query}&quotesCount=5&newsCount=0"
            yahoo_req = urllib.request.Request(yahoo_url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(yahoo_req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                quotes = data.get("quotes", [])
                
                for q in quotes:
                    if q.get("quoteType") in ["EQUITY", "ETF"]:
                        sym = q.get("symbol", "")
                        
                        # 네이버 검색 결과에 이미 있는 종목은 제외 (중복 방지)
                        if any(r.symbol == sym for r in results):
                            continue

                        name_eng = q.get("shortname") or q.get("longname") or sym
                        _, name = resolve_stock_name(sym.upper(), name_eng)

                        results.append(
                            SearchResult(
                                symbol=sym,
                                shortname=name,
                                longname=name_eng,
                                exchange=q.get("exchange", "")
                            )
                        )
        except Exception as e:
            print(f"Yahoo Search Error: {e}")

        return SearchResponse(results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@app.get("/api/quote/{symbol}", response_model=QuoteResponse)
def get_quote(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        
        # 1. 실시간/최신 시세를 정확히 가져오기 위해 fast_info 및 history 우선 활용
        # yfinance의 .info는 캐싱 이슈로 인해 가격이 누락되거나 지연되는 경우가 많습니다.
        price, prev_close = None, None
        
        try:
            fast_info = ticker.fast_info
            if fast_info is not None:
                price = _safe_number(getattr(fast_info, "last_price", None))
                prev_close = _safe_number(getattr(fast_info, "previous_close", None))
        except Exception:
            pass

        # fast_info에서 못 가져왔다면 history(최근 5일) 데이터로 보완
        if price is None or prev_close is None:
            try:
                hist = ticker.history(period="5d")
                if not hist.empty:
                    if price is None:
                        price = _safe_number(hist["Close"].iloc[-1])
                    if prev_close is None and len(hist) >= 2:
                        prev_close = _safe_number(hist["Close"].iloc[-2])
            except Exception:
                pass

        # yfinance info 요청이 실패하더라도 전체가 뻗지 않도록 방어
        try:
            info = ticker.info or {}
        except Exception as e:
            print(f"⚠️ {symbol} info 데이터 로드 실패: {e}")
            info = {}

        # 2. 위 방법으로도 실패했다면 기존처럼 info에서 가져오기
        if price is None:
            price = _safe_number(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
        if prev_close is None:
            prev_close = _safe_number(info.get("previousClose") or info.get("regularMarketPreviousClose"))
        change = price - prev_close if price is not None and prev_close is not None else None
        change_pct = (
            (change / prev_close * 100.0)
            if change is not None and prev_close not in (None, 0)
            else None
        )

        high52w = _safe_number(info.get("fiftyTwoWeekHigh"))
        sector_eng = info.get("sector") or info.get("quoteType") or "N/A"
        sector = SECTOR_TRANSLATIONS.get(sector_eng, sector_eng)

        name_eng = info.get("shortName") or info.get("longName") or symbol
        _, name = resolve_stock_name(symbol.upper(), name_eng)

        exchange_raw = info.get("exchange", "")
        if "Nasdaq" in exchange_raw or exchange_raw == "NMS":
            exchange_formatted = "NASDAQ"
        elif "NYSE" in exchange_raw or exchange_raw == "NYQ":
            exchange_formatted = "NYSE"
        elif symbol.endswith(".KS") or exchange_raw == "KSC":
            exchange_formatted = "KOSPI"
        elif symbol.endswith(".KQ") or exchange_raw == "KOE":
            exchange_formatted = "KOSDAQ"
        else:
            exchange_formatted = "US"

        # 1. Try to get all financials from the fast .info object first
        revenue = info.get("totalRevenue")
        operating_margin = info.get("operatingMargins")
        eps = info.get("trailingEps") or info.get("forwardEps")
        pe = info.get("trailingPE") or info.get("forwardPE")
        pbr = info.get("priceToBook")
        roe = info.get("returnOnEquity")

        # 2. For domestic stocks, .info is often incomplete.
        # If key metrics are missing, fetch from detailed statements as a fallback.
        if symbol.endswith((".KS", ".KQ")) and any(v is None for v in [revenue, operating_margin, roe]):
            try:
                financials_df = ticker.financials
                balance_sheet_df = ticker.balance_sheet

                if not financials_df.empty:
                    latest_financials = financials_df.iloc[:, 0]
                    
                    if revenue is None and 'Total Revenue' in latest_financials:
                        revenue = latest_financials['Total Revenue']

                    if operating_margin is None and 'Operating Income' in latest_financials and revenue is not None and revenue > 0:
                        operating_margin = latest_financials['Operating Income'] / revenue
                    
                    if roe is None and 'Net Income' in latest_financials and not balance_sheet_df.empty:
                        latest_balance_sheet = balance_sheet_df.iloc[:, 0]
                        equity_key = next((k for k in ['Stockholder Equity', 'Total Stockholder Equity'] if k in latest_balance_sheet), None)
                        if equity_key:
                            equity = latest_balance_sheet[equity_key]
                            if equity and equity > 0:
                                roe = latest_financials['Net Income'] / equity
            except Exception as e:
                print(f"Could not fetch detailed financials for {symbol}: {e}")
                pass

        currency = info.get("currency") or "USD"

        price_krw = None
        if price is not None:
            if currency == "USD":
                price_krw = price * get_usd_to_krw()
            elif currency == "KRW":
                price_krw = price

        fin = Financials(
            revenue=str(revenue) if revenue is not None else "-",
            operatingIncome=str(operating_margin) if operating_margin is not None else "-",
            eps=str(eps) if eps is not None else "-",
            per=str(pe) if pe is not None else "-",
            pbr=str(pbr) if pbr is not None else "-",
            roe=str(roe) if roe is not None else "-",
        )
        
        earnings_ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        earnings_date = datetime.fromtimestamp(earnings_ts).strftime('%Y-%m-%d') if earnings_ts else "-"
        
        inst_hold = info.get("heldPercentInstitutions")
        institution_pct = f"{inst_hold * 100:.2f}%" if inst_hold else "-"
        
        business_summary = _business_summary_cache.get(symbol)
        
        if not business_summary:
            raw_summary = info.get("longBusinessSummary")
            
            if not raw_summary and symbol.endswith((".KS", ".KQ")):
                try:
                    clean_code = symbol.split(".")[0]
                    url = f"https://m.stock.naver.com/api/stock/{clean_code}/integration"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=3) as res:
                        data = json.loads(res.read().decode('utf-8'))
                        raw_summary = data.get("corpSummary")
                except Exception:
                    pass

            if raw_summary:
                summary_text = raw_summary.replace('\n', ' ').replace('\r', '').strip()
                
                # (API 무료 할당량 초과 에러 429 방지를 위해 백그라운드 AI 요약 기능은 비활성화합니다)

                if not business_summary:
                    if not re.search(r'[가-힣]', summary_text):
                        short_eng = summary_text[:250]
                        last_dot = short_eng.rfind('. ')
                        if last_dot > 0:
                            short_eng = short_eng[:last_dot+1]
                        
                        if translator:
                            try:
                                translated = translator.translate(short_eng, dest='ko').text
                                if translated and translated != short_eng and re.search(r'[가-힣]', translated):
                                    summary_text = translated
                            except Exception:
                                pass
                    
                    if re.search(r'[가-힣]', summary_text):
                        match = re.search(r'(.*?다\.)', summary_text)
                        if match:
                            business_summary = match.group(1).strip()
                        else:
                            business_summary = summary_text[:80] + ("..." if len(summary_text) > 80 else "")
                    else:
                        business_summary = "해외 기업 정보를 한글로 번역하는 중 지연이 발생했습니다. (잠시 후 다시 시도해주세요)"
                        
                _business_summary_cache[symbol] = business_summary

        news_data = []
        try:
            # 1. 구글 뉴스 RSS를 통해 한국어 및 최신 뉴스를 안정적으로 가져옵니다.
            query = f"{name} 주식"
            safe_query = urllib.parse.quote(query)
            rss_url = f"https://news.google.com/rss/search?q={safe_query}&hl=ko&gl=KR&ceid=KR:ko"
            news_req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(news_req, timeout=5) as response:
                root = ET.fromstring(response.read())
                for item in root.findall('./channel/item')[:3]:
                    title = item.find('title').text if item.find('title') is not None else "제목 없음"
                    link = item.find('link').text if item.find('link') is not None else "#"
                    source_elem = item.find('source')
                    publisher = source_elem.text if source_elem is not None else "Google News"
                    
                    pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else ""
                    pub_time = 0
                    if pub_date_str:
                        try:
                            dt = parsedate_to_datetime(pub_date_str)
                            pub_time = int(dt.timestamp())
                        except Exception:
                            pass
                            
                    news_data.append(NewsItem(title=title, publisher=publisher, link=link, publishTime=pub_time))
        except Exception as e:
            print(f"Google News fetch error for {symbol}: {e}")
            # 2. 실패 시 yfinance 기본 뉴스로 대체
            try:
                raw_news = ticker.news
                if raw_news:
                    for n in raw_news[:3]:
                        news_data.append(NewsItem(
                            title=n.get("title", "제목 없음"),
                            publisher=n.get("publisher", "알 수 없음"),
                            link=n.get("link", "#"),
                            publishTime=n.get("providerPublishTime", 0)
                        ))
            except Exception:
                pass

        return QuoteResponse(
            symbol=symbol,
            name=name,
            sector=sector,
            exchange=exchange_formatted,
            price=price,
            priceKrw=price_krw,
            change=change,
            changePct=change_pct,
            high52w=high52w,
            currency=currency,
            financials=fin,
            earningsDate=earnings_date,
            institutionHoldPct=institution_pct,
            businessSummary=business_summary,
            news=news_data,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()  # 상세 에러 로그를 터미널에 출력
        raise HTTPException(status_code=500, detail=f"Failed to fetch quote: {e}")


@app.get("/api/chart/{symbol}", response_model=ChartResponse)
def get_chart(
    symbol: str,
    interval: str = "1d",
):
    try:
        # 야후 파이낸스는 간격(interval)에 따라 조회 가능한 최대 기간(period)이 다릅니다.
        # 이 제한을 초과해서 요청하면 빈 데이터(에러)가 반환되어 차트가 뜨지 않습니다.
        if interval == "1m":
            period = "7d"
        elif interval in ["2m", "5m", "15m", "30m", "90m"]:
            period = "60d"
        elif interval in ["60m", "1h"]:
            period = "730d"
        else:
            period = "max"

        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False
        )

        if df.empty:
            return ChartResponse(symbol=symbol, interval=interval, data=[])

        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)

        points: List[ChartPoint] = []
        for idx, row in df.iterrows():
            if interval in ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"]:
                dt_str = idx.strftime("%Y-%m-%d %H:%M")
            else:
                dt_str = idx.strftime("%Y-%m-%d")
            points.append(
                ChartPoint(
                    date=dt_str,
                    open=_safe_number(row.get("Open")),
                    high=_safe_number(row.get("High")),
                    low=_safe_number(row.get("Low")),
                    close=_safe_number(row.get("Close")),
                    volume=_safe_number(row.get("Volume")),
                )
            )

        return ChartResponse(symbol=symbol, interval=interval, data=points)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch chart: {e}")

@app.get("/api/investor-trend/{symbol}", response_model=List[InvestorTrend])
def get_investor_trend(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="10d")
        if hist.empty:
            return []
            
        if hasattr(hist.columns, "levels") and len(hist.columns.levels) > 1:
            hist.columns = hist.columns.get_level_values(0)
            
        trends = []
        for date, row in hist.iterrows():
            dt_str = date.strftime("%Y-%m-%d")
            change = row.get("Close", 0) - row.get("Open", 0)
            vol = row.get("Volume", 0)
            
            # 야후 API에는 일별 상세 수급 데이터가 없으므로 거래량과 주가 방향성을 기반으로 추정치를 시뮬레이션합니다.
            base_net = vol * 0.05
            random.seed(symbol + dt_str) # 종목과 날짜에 대해 항상 동일한 결과가 나오도록 시드 고정
            
            direction = 1 if change >= 0 else -1
            for_net = base_net * random.uniform(0.1, 1.2) * direction
            inst_net = base_net * random.uniform(0.1, 0.8) * direction
            ret_net = -(for_net + inst_net) + (base_net * random.uniform(-0.05, 0.05))
            
            trends.append(
                InvestorTrend(
                    date=dt_str, retail=round(ret_net),
                    foreigner=round(for_net), institution=round(inst_net),
                    priceChange=round(change, 2)
                )
            )
        return trends
    except Exception as e:
        print(f"Trend Error: {e}")
        return []

@app.get("/api/top-kr-stocks")
def get_top_kr_stocks():
    results = []
    try:
        # 코스피 시총 상위 100개만 조회 (Vercel 10초 타임아웃 방지)
        for page in range(1, 2):
            req = urllib.request.Request(f"https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page={page}&pageSize=100", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                stocks = data.get("stocks", [])
                if not stocks: break
                for item in stocks:
                    sym = f"{item['itemCode']}.KS"
                    name = item['stockName']
                    _us_stock_name_cache[sym] = name
                    results.append({"symbol": sym, "name": name})
        # 코스닥 시총 상위 100개만 조회 (Vercel 10초 타임아웃 방지)
        for page in range(1, 2):
            req = urllib.request.Request(f"https://m.stock.naver.com/api/stocks/marketValue/KOSDAQ?page={page}&pageSize=100", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                stocks = data.get("stocks", [])
                if not stocks: break
                for item in stocks:
                    sym = f"{item['itemCode']}.KQ"
                    name = item['stockName']
                    _us_stock_name_cache[sym] = name
                    results.append({"symbol": sym, "name": name})
    except Exception as e:
        print(f"Top KR Stocks Error: {e}")
    return results

@app.get("/api/top-us-stocks")
def get_top_us_stocks():
    results = []
    try:
        import urllib.request
        import pandas as pd
        import io
        req = urllib.request.Request("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
        dfs = pd.read_html(io.StringIO(html))
        df = dfs[0]
        
        raw_list = []
        # 시총 상위 100개까지만 잘라서 처리하여 성능 최적화
        for _, row in df.head(100).iterrows():
            sym = str(row['Symbol']).replace('.', '-') # BRK.B 같은 종목을 야후 파이낸스 규격(BRK-B)으로 변환
            name = str(row['Security'])
            raw_list.append((sym, name))
            
        temp_results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(resolve_stock_name, sym, name): sym for sym, name in raw_list}
            for future in concurrent.futures.as_completed(futures):
                try:
                    s, ko_n = future.result()
                    temp_results[s] = ko_n
                except Exception:
                    pass
                    
        for sym, name in raw_list:
            results.append({"symbol": sym, "name": temp_results.get(sym, name)})
    except Exception as e:
        print(f"Top US Stocks Error: {e}")
    return results

@app.get("/api/top-us-ndx")
def get_top_us_ndx():
    results = []
    try:
        import urllib.request
        import pandas as pd
        import io
        req = urllib.request.Request("https://en.wikipedia.org/wiki/Nasdaq-100", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
        dfs = pd.read_html(io.StringIO(html))
        df = None
        for table in dfs:
            if 'Ticker' in table.columns or 'Symbol' in table.columns:
                df = table
                break
        if df is not None:
            sym_col = 'Ticker' if 'Ticker' in df.columns else 'Symbol'
            name_col = 'Company' if 'Company' in df.columns else 'Security'
                
            raw_list = []
            # NDX 상위 50개까지만 잘라서 처리하여 성능 최적화
            for _, row in df.head(50).iterrows():
                sym = str(row[sym_col]).replace('.', '-')
                name = str(row[name_col])
                raw_list.append((sym, name))
                
            temp_results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(resolve_stock_name, sym, name): sym for sym, name in raw_list}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        s, ko_n = future.result()
                        temp_results[s] = ko_n
                    except Exception:
                        pass
                        
            for sym, name in raw_list:
                results.append({"symbol": sym, "name": temp_results.get(sym, name)})
    except Exception as e:
        print(f"Top US NDX Error: {e}")
    return results