# HGU 졸업 Project — 캠퍼스 안내 AR/VR 투어

## 기본 정보

- **기간**: 2017.07 – 2018.05
- **분류**: 한동대학교 졸업 프로젝트 (MixedReality)
- **영상**: https://youtu.be/HnoxcLM8ksU

## 프로젝트 소개

VR과 AR을 융합한 MR 환경으로 만든 캠퍼스 안내 투어 프로그램.
Marker + Markerless 기술을 융합하고 Google Maps GPS와 결합하여 실제 캠퍼스를 탐험하는 가이드 캐릭터 기반 투어를 구현했습니다.

## 기술 스택

- Unity
- Vuforia SDK (Marker / Markerless AR)
- Samsung Gear VR
- Google Maps API (GPS)
- Android SDK

## 핵심 구현

**Marker 인식 방식 선정**
HOG, SIFT, SURF, Vuforia SDK를 비교 실험 (인식률 80% 이상, 움직임 내 안정성, 성능 3가지 기준).
결과적으로 Vuforia SDK 채택 — GPS의 부족한 부분 보완 + Markerless 위치 정확도 30% 향상.

**게임 로직**
- 가이드 캐릭터(호랑이)가 사용자 우측에 증강되어 목적지까지 안내
- 목적지 도달 시 장소 설명 제공, 모든 Stage Clear 시 종료
- 먹이주기 / 성장하기 등 캐릭터 육성 요소로 재미 부여

**컨트롤러 방식 3가지 구현**
1. HMD 머리 움직임으로 마우스 포인터 제어
2. Samsung Gear VR 컨트롤러 블루투스 연동
3. Gear VR 기기 측면 터치패드 드래그 (최종 채택)

## 팀 구성

| 이름 | 역할 |
|------|------|
| 정병권 | 팀장 · Google Maps GPS |
| 박예린 | UX/UI 디자인 총괄 · 캐릭터 모델링 |
| 이상호 (me) | Unity 개발 · Marker/Markerless 구현 · AR↔VR 전환 · 게임 로직 |
| 임예린 | Unity 개발 · 게임 로직 · 컨트롤러 조작 구현 |
