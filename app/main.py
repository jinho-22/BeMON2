from fastapi import FastAPI, Form, Request, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import get_db
from app.models.models import Report, ErrorReport, MspReport, LogReport, User
from fastapi.templating import Jinja2Templates
from math import ceil
from datetime import datetime
import io
import csv
from starlette.middleware.sessions import SessionMiddleware
from urllib.parse import urlencode



router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecret123")


app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(router)

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("main.html", {"request": request})

@app.get("/msp", response_class=HTMLResponse)
async def msp_page(request: Request):
    return templates.TemplateResponse("report/msp.html", {"request": request})

@app.get("/error", response_class=HTMLResponse)
async def error_page(request: Request):
    return templates.TemplateResponse("report/error.html", {"request": request})

@app.get("/log", response_class=HTMLResponse)
async def log_page(request: Request):
    return templates.TemplateResponse("report/log.html", {"request": request})

# @app.get("/reports", response_class=HTMLResponse)
# def report_list(request: Request, page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
#     offset = (page - 1) * limit
#     total = db.query(MspReport).count()
#     total_pages = ceil(total / limit)

#     # 최대 5개의 페이징 번호만 표시
#     start_page = max(1, page - 2)
#     end_page = min(start_page + 4, total_pages)
#     start_page = max(1, end_page - 4)  # 끝 범위로 인해 start_page가 다시 줄어들 수 있음

#     reports = db.query(MspReport)\
#                 .order_by(MspReport.request_date.desc())\
#                 .offset(offset).limit(limit).all()

#     return templates.TemplateResponse("report/report_list.html", {
#         "request": request,
#         "reports": reports,
#         "page": page,
#         "total_pages": total_pages,
#         "start_page": start_page,
#         "end_page": end_page
#     })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login/login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if user:
        request.session["user_id"] = user.user_id
        request.session["username"] = user.username
        return RedirectResponse(url="/", status_code=303)
    else:
        return templates.TemplateResponse("login/login.html", {
            "request": request,
            "error": "아이디 또는 비밀번호가 잘못되었습니다."
        })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("login/register.html", {"request": request})

@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    email: str = Form(None),
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return templates.TemplateResponse("login/register.html", {"request": request, "error": "이미 존재하는 아이디입니다."})

    new_user = User(
        username=username,
        password=password,
        name=name,
        email=email,
        created_at=datetime.now()
    )
    db.add(new_user)
    db.commit()

    return RedirectResponse(url="/login", status_code=303)


@app.get("/report/{report_id}", response_class=HTMLResponse)
def report_detail_page(request: Request, report_id: int, db: Session = Depends(get_db)):
    report_entry = db.query(Report).filter(Report.report_id == report_id).first()
    if not report_entry:
        raise HTTPException(status_code=404, detail="Report not found")

    report_type = report_entry.report_type
    if report_type == "msp":
        report = db.query(MspReport).filter(MspReport.report_id == report_id).first()
    elif report_type == "error":
        report = db.query(ErrorReport).filter(ErrorReport.report_id == report_id).first()
    elif report_type == "log":
        report = db.query(LogReport).filter(LogReport.report_id == report_id).first()
    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    if not report:
        raise HTTPException(status_code=404, detail="Detailed report not found")

    return templates.TemplateResponse("report/report_detail.html", {
        "request": request,
        "report_type": report_type,
        "report": report
    })





@app.post("/msp/submit")
async def submit_msp(
    request: Request,
    manager: str = Form(...),
    request_date: str = Form(...),
    request_time: str = Form(...),
    completed_date: str = Form(None),
    completed_time: str = Form(None),
    client_name: str = Form(...),
    system_name: str = Form(...),
    target_env: str = Form(None),
    requester: str = Form(...),
    request_type: str = Form(...),
    request_content: str = Form(None),
    purpose: str = Form(None),
    response: str = Form(None),
    etc: str = Form(None),
    status: str = Form(None),
    db: Session = Depends(get_db)
):
    # 날짜+시간 합치기
    request_datetime = datetime.strptime(f"{request_date} {request_time}", "%Y-%m-%d %H:%M")
    completed_datetime = None
    if completed_date and completed_time:
        completed_datetime = datetime.strptime(f"{completed_date} {completed_time}", "%Y-%m-%d %H:%M")

    # 1. report 테이블 insert
    report = Report(
        create_by=1,  # TODO: 로그인한 사용자 ID로 수정
        report_type="msp",
        created_at=datetime.now()
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 2. msp_report 테이블 insert
    msp_report = MspReport(
        report_id=report.report_id,
        manager=manager,
        request_date=request_datetime,
        completed_date=completed_datetime,
        client_name=client_name,
        system_name=system_name,
        target_env=target_env,
        requester=requester,
        request_type=request_type,
        request_content=request_content,
        purpose=purpose,
        response=response,
        etc=etc,
        status=status
    )
    db.add(msp_report)
    db.commit()

    return RedirectResponse(url="/msp", status_code=303)


@app.post("/error/submit")
async def submit_error(
    request: Request,
    manager: str = Form(...),
    status: str = Form(None),
    error_start_date: str = Form(...),
    start_time: str = Form(...),
    error_end_date: str = Form(None),
    end_time: str = Form(None),
    client_name: str = Form(...),
    system_name: str = Form(...),
    target_env: str = Form(None),
    target_component: str = Form(None),
    customer_impact: str = Form(None),
    error_info: str = Form(...),
    error_reason: str = Form(None),
    action_taken: str = Form(None),
    etc: str = Form(None),
    db: Session = Depends(get_db)
):
    # 1. report 테이블에 insert
    report = Report(
        create_by=1,  # TODO: 로그인 사용자로 교체
        report_type="error",
        created_at=datetime.now()
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 2. 장애 시작일+시간 합치기
    error_start_dt = None
    if error_start_date and start_time:
        error_start_dt = datetime.strptime(f"{error_start_date} {start_time}", "%Y-%m-%d %H:%M")

    # 3. 장애 종료일+시간 합치기
    error_end_dt = None
    if error_end_date and end_time:
        error_end_dt = datetime.strptime(f"{error_end_date} {end_time}", "%Y-%m-%d %H:%M")

    # 4. error_report 테이블에 insert
    error_report = ErrorReport(
        report_id=report.report_id,
        manager=manager,
        status=status,
        error_start_date=error_start_dt,
        error_end_date=error_end_dt,
        client_name=client_name,
        system_name=system_name,
        target_env=target_env,
        target_component=target_component,
        customer_impact=customer_impact,
        error_info=error_info,
        error_reason=error_reason,
        action_taken=action_taken,
        etc=etc
    )
    db.add(error_report)
    db.commit()

    return RedirectResponse(url="/error_reports", status_code=303)

@app.post("/log/submit")
async def submit_log(
    request: Request,
    manager: str = Form(...),
    status: str = Form(None),
    log_date: str = Form(...),
    log_time: str = Form(...),
    completed_date: str = Form(None),
    completed_time: str = Form(None),
    client_name: str = Form(...),
    system_name: str = Form(...),
    target_env: str = Form(None),
    log_type: str = Form(...),
    content: str = Form(...),
    action: str = Form(None),
    summary: str = Form(None),
    etc: str = Form(None),
    db: Session = Depends(get_db)
):
    from datetime import datetime

    # log_date + log_time 합치기
    log_datetime = datetime.strptime(f"{log_date} {log_time}", "%Y-%m-%d %H:%M")
    completed_datetime = None
    if completed_date and completed_time:
        completed_datetime = datetime.strptime(f"{completed_date} {completed_time}", "%Y-%m-%d %H:%M")

    # report 테이블에 insert
    report = Report(
        create_by=1,
        report_type="log",
        created_at=datetime.now()
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # log_report 테이블에 insert
    log_report = LogReport(
        report_id=report.report_id,
        manager=manager,
        status=status,
        log_date=log_datetime,
        completed_date=completed_datetime,
        client_name=client_name,
        system_name=system_name,
        target_env=target_env,
        log_type=log_type,
        content=content,
        action=action,
        summary=summary,
        etc=etc
    )
    db.add(log_report)
    db.commit()

    return RedirectResponse(url="/log_reports", status_code=303)




# @app.get("/error_reports", response_class=HTMLResponse)
# def error_report_list(request: Request, page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
#     offset = (page - 1) * limit
#     total = db.query(ErrorReport).count()
#     total_pages = ceil(total / limit)

#     # 최대 5개의 페이징 번호만 표시
#     start_page = max(1, page - 2)
#     end_page = min(start_page + 4, total_pages)
#     start_page = max(1, end_page - 4)

#     reports = db.query(ErrorReport)\
#                 .order_by(ErrorReport.error_start_date.desc())\
#                 .offset(offset).limit(limit).all()

#     return templates.TemplateResponse("report/error_report_list.html", {
#         "request": request,
#         "reports": reports,
#         "page": page,
#         "total_pages": total_pages,
#         "start_page": start_page,
#         "end_page": end_page
#     })


# @app.get("/log_reports", response_class=HTMLResponse)
# def log_report_list(request: Request, page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
#     offset = (page - 1) * limit
#     total = db.query(LogReport).count()
#     total_pages = ceil(total / limit)

#     # 최대 5개의 페이징 번호만 표시
#     start_page = max(1, page - 2)
#     end_page = min(start_page + 4, total_pages)
#     start_page = max(1, end_page - 4)

#     reports = db.query(LogReport).order_by(LogReport.log_date.desc()).offset(offset).limit(limit).all()

#     return templates.TemplateResponse("report/log_reports.html", {
#         "request": request,
#         "reports": reports,
#         "page": page,
#         "total_pages": total_pages,
#         "start_page": start_page,
#         "end_page": end_page
#     })


@app.get("/msp_reports/download")
async def download_msp_csv(request: Request, start_date: str, end_date: str, db: Session = Depends(get_db)):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    reports = db.query(MspReport).filter(MspReport.request_date.between(start, end)).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # [✅ 올바른 헤더 순서]
    writer.writerow([
        "요청일자", "고객사", "시스템명", "대상 환경",
        "요청자", "요청유형", "요청내용", "목적",
        "담당자", "상태", "완료일자", "응답", "비고"
    ])

    for r in reports:
        writer.writerow([
            r.request_date.strftime("%Y-%m-%d %H:%M") if r.request_date else '',
            r.client_name or '',
            r.system_name or '',
            r.target_env or '',
            r.requester or '',
            r.request_type or '',
            r.request_content or '',
            r.purpose or '',
            r.manager or '',
            r.status or '',
            r.completed_date.strftime("%Y-%m-%d %H:%M") if r.completed_date else '',
            r.response or '',
            r.etc or ''
        ])

    output.seek(0)

    # BOM 추가해서 한글 깨짐 방지
    bom = '\ufeff'
    csv_content = bom + output.getvalue()

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=msp_reports.csv"}
    )


@app.get("/error_reports/download")
async def download_error_csv(request: Request, start_date: str, end_date: str, db: Session = Depends(get_db)):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    reports = db.query(ErrorReport).filter(ErrorReport.error_start_date.between(start, end)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["장애일자", "고객사", "시스템명", "대상 환경", "장애대상", "고객 영향도", "장애내용", "장애원인", "조치내용", "담당자", "상태", "장애종료일자", "비고"])

    for r in reports:
        writer.writerow([
            r.error_start_date.strftime("%Y-%m-%d %H:%M") if r.error_start_date else '',
            r.client_name or '',
            r.system_name or '',
            r.target_env or '',
            r.target_component or '',
            r.customer_impact or '',
            r.error_info or '',
            r.error_reason or '',
            r.action_taken or '',
            r.manager or '',
            r.status or '',
            r.error_end_date.strftime("%Y-%m-%d %H:%M") if r.error_end_date else '',
            r.etc or ''
        ])

    output.seek(0)
    bom = '\ufeff'
    return Response(
        content=bom + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=error_reports.csv"}
    )


@app.get("/log_reports/download")
async def download_log_csv(request: Request, start_date: str, end_date: str, db: Session = Depends(get_db)):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    reports = db.query(LogReport).filter(LogReport.log_date.between(start, end)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["로그일자", "고객사", "시스템명", "대상 환경", "유형", "내용", "조치", "담당자", "상태", "완료일자", "요약", "비고"])

    for r in reports:
        writer.writerow([
            r.log_date.strftime("%Y-%m-%d %H:%M") if r.log_date else '',
            r.client_name or '',
            r.system_name or '',
            r.target_env or '',
            r.log_type or '',
            r.content or '',
            r.action or '',
            r.manager or '',
            r.status or '',
            r.completed_date.strftime("%Y-%m-%d %H:%M") if r.completed_date else '',
            r.summary or '',
            r.etc or ''
        ])

    output.seek(0)
    bom = '\ufeff'
    return Response(
        content=bom + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=log_reports.csv"}
    )

# 수정폼 보여주기
@app.get("/report/{report_id}/edit", response_class=HTMLResponse)
async def report_edit_page(request: Request, report_id: int, db: Session = Depends(get_db)):
    report_entry = db.query(Report).filter(Report.report_id == report_id).first()
    if not report_entry:
        raise HTTPException(status_code=404, detail="Report not found")

    report_type = report_entry.report_type
    if report_type == "msp":
        report = db.query(MspReport).filter(MspReport.report_id == report_id).first()
    elif report_type == "error":
        report = db.query(ErrorReport).filter(ErrorReport.report_id == report_id).first()
    elif report_type == "log":
        report = db.query(LogReport).filter(LogReport.report_id == report_id).first()
    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    return templates.TemplateResponse("report/report_edit.html", {
        "request": request,
        "report_type": report_type,
        "report": report
    })


# 수정 저장 처리
@app.post("/report/{report_id}/edit")
async def report_edit(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
    # form 데이터는 동적으로 받기 위해 request.form() 직접 파싱할 거야
):
    form = await request.form()
    report_entry = db.query(Report).filter(Report.report_id == report_id).first()
    if not report_entry:
        raise HTTPException(status_code=404, detail="Report not found")

    report_type = report_entry.report_type

    if report_type == "msp":
        report = db.query(MspReport).filter(MspReport.report_id == report_id).first()
        if report:
            report.manager = form.get("manager")
            report.status = form.get("status")
            report.request_date = datetime.strptime(form.get("request_date") + " " + form.get("request_time"), "%Y-%m-%d %H:%M")
            completed_date = form.get("completed_date")
            completed_time = form.get("completed_time")
            if completed_date and completed_time:
                report.completed_date = datetime.strptime(completed_date + " " + completed_time, "%Y-%m-%d %H:%M")
            else:
                report.completed_date = None
            report.client_name = form.get("client_name")
            report.system_name = form.get("system_name")
            report.target_env = form.get("target_env")
            report.requester = form.get("requester")
            report.request_type = form.get("request_type")
            report.request_content = form.get("request_content")
            report.purpose = form.get("purpose")
            report.response = form.get("response")
            report.etc = form.get("etc")
    elif report_type == "error":
        report = db.query(ErrorReport).filter(ErrorReport.report_id == report_id).first()
        if report:
            report.manager = form.get("manager")
            report.status = form.get("status")
            report.error_start_date = datetime.strptime(form.get("error_start_date") + " " + form.get("start_time"), "%Y-%m-%d %H:%M")
            error_end_date = form.get("error_end_date")
            end_time = form.get("end_time")
            if error_end_date and end_time:
                report.error_end_date = datetime.strptime(error_end_date + " " + end_time, "%Y-%m-%d %H:%M")
            else:
                report.error_end_date = None
            report.client_name = form.get("client_name")
            report.system_name = form.get("system_name")
            report.target_env = form.get("target_env")
            report.target_component = form.get("target_component")
            report.customer_impact = form.get("customer_impact")
            report.error_info = form.get("error_info")
            report.error_reason = form.get("error_reason")
            report.action_taken = form.get("action_taken")
            report.etc = form.get("etc")
    elif report_type == "log":
        report = db.query(LogReport).filter(LogReport.report_id == report_id).first()
        if report:
            report.manager = form.get("manager")
            report.status = form.get("status")
            report.log_date = datetime.strptime(form.get("log_date") + " " + form.get("log_time"), "%Y-%m-%d %H:%M")
            completed_date = form.get("completed_date")
            completed_time = form.get("completed_time")
            if completed_date and completed_time:
                report.completed_date = datetime.strptime(completed_date + " " + completed_time, "%Y-%m-%d %H:%M")
            else:
                report.completed_date = None
            report.client_name = form.get("client_name")
            report.system_name = form.get("system_name")
            report.target_env = form.get("target_env")
            report.log_type = form.get("log_type")
            report.content = form.get("content")
            report.action = form.get("action")
            report.summary = form.get("summary")
            report.etc = form.get("etc")

    db.commit()

    return RedirectResponse(url=f"/report/{report_id}", status_code=303)


# 삭제 처리
@app.post("/report/{report_id}/delete")
async def report_delete(report_id: int, db: Session = Depends(get_db)):
    report_entry = db.query(Report).filter(Report.report_id == report_id).first()
    if not report_entry:
        raise HTTPException(status_code=404, detail="Report not found")

    report_type = report_entry.report_type

    # 세부 테이블 먼저 삭제
    if report_type == "msp":
        db.query(MspReport).filter(MspReport.report_id == report_id).delete()
    elif report_type == "error":
        db.query(ErrorReport).filter(ErrorReport.report_id == report_id).delete()
    elif report_type == "log":
        db.query(LogReport).filter(LogReport.report_id == report_id).delete()

    # 그 다음 report 테이블 삭제
    db.delete(report_entry)
    db.commit()

    # 삭제 후 목록으로 이동
    if report_type == "msp":
        return RedirectResponse(url="/reports", status_code=303)
    elif report_type == "error":
        return RedirectResponse(url="/error_reports", status_code=303)
    elif report_type == "log":
        return RedirectResponse(url="/log_reports", status_code=303)

@app.get("/reports", response_class=HTMLResponse)
def report_list(
    request: Request,
    page: int = 1,
    limit: int = 10,
    search: str = "",           # ✅ 추가
    manager: str = "",
    requester: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    request_type: str = "",
    start_date: str = "",
    end_date: str = "",
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    query = db.query(MspReport)

    # ✅ 통합 검색어 조건 추가
    if search:
        query = query.filter(
            (MspReport.manager.contains(search)) |
            (MspReport.requester.contains(search)) |
            (MspReport.client_name.contains(search)) |
            (MspReport.system_name.contains(search)) |
            (MspReport.target_env.contains(search)) |
            (MspReport.request_type.contains(search)) |
            (MspReport.request_content.contains(search))
        )

    # ✅ 기존 필터 조건
    if manager:
        query = query.filter(MspReport.manager.contains(manager))
    if requester:
        query = query.filter(MspReport.requester.contains(requester))
    if status:
        query = query.filter(MspReport.status == status)
    if client_name:
        query = query.filter(MspReport.client_name.contains(client_name))
    if system_name:
        query = query.filter(MspReport.system_name.contains(system_name))
    if target_env:
        query = query.filter(MspReport.target_env.contains(target_env))
    if request_type:
        query = query.filter(MspReport.request_type.contains(request_type))
    if start_date and end_date:
        query = query.filter(
            MspReport.request_date.between(start_date + " 00:00:00", end_date + " 23:59:59")
        )

    total = query.count()
    total_pages = ceil(total / limit)
    start_page = max(1, page - 2)
    end_page = min(start_page + 4, total_pages)
    start_page = max(1, end_page - 4)

    reports = query.order_by(MspReport.request_date.desc()).offset(offset).limit(limit).all()

    # ✅ query string 다시 만들기
    query_dict = {
        "search": search,
        "manager": manager,
        "requester": requester,
        "status": status,
        "client_name": client_name,
        "system_name": system_name,
        "target_env": target_env,
        "request_type": request_type,
        "start_date": start_date,
        "end_date": end_date
    }
    filtered_query = {k: v for k, v in query_dict.items() if v}
    query_string = urlencode(filtered_query)

    return templates.TemplateResponse("report/report_list.html", {
        "request": request,
        "reports": reports,
        "page": page,
        "total_pages": total_pages,
        "start_page": start_page,
        "end_page": end_page,
        "query_string": query_string
    })



@app.get("/error_reports", response_class=HTMLResponse)
def error_report_list(
    request: Request,
    page: int = 1,
    limit: int = 10,
    search: str = "",         # ✅ 추가
    manager: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    target_component: str = "",
    start_date: str = "",
    end_date: str = "",
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    query = db.query(ErrorReport)

    # ✅ 통합 검색어 조건 추가
    if search:
        query = query.filter(
            (ErrorReport.manager.contains(search)) |
            (ErrorReport.client_name.contains(search)) |
            (ErrorReport.system_name.contains(search)) |
            (ErrorReport.target_env.contains(search)) |
            (ErrorReport.target_component.contains(search)) |
            (ErrorReport.error_info.contains(search))
        )

    # ✅ 기존 필터 조건
    if manager:
        query = query.filter(ErrorReport.manager.contains(manager))
    if status:
        query = query.filter(ErrorReport.status == status)
    if client_name:
        query = query.filter(ErrorReport.client_name.contains(client_name))
    if system_name:
        query = query.filter(ErrorReport.system_name.contains(system_name))
    if target_env:
        query = query.filter(ErrorReport.target_env.contains(target_env))
    if target_component:
        query = query.filter(ErrorReport.target_component.contains(target_component))
    if start_date and end_date:
        query = query.filter(
            ErrorReport.error_start_date.between(start_date + " 00:00:00", end_date + " 23:59:59")
        )

    total = query.count()
    total_pages = ceil(total / limit)
    start_page = max(1, page - 2)
    end_page = min(start_page + 4, total_pages)
    start_page = max(1, end_page - 4)

    reports = query.order_by(ErrorReport.error_start_date.desc()).offset(offset).limit(limit).all()

    query_dict = {
        "search": search,
        "manager": manager,
        "status": status,
        "client_name": client_name,
        "system_name": system_name,
        "target_env": target_env,
        "target_component": target_component,
        "start_date": start_date,
        "end_date": end_date
    }
    filtered_query = {k: v for k, v in query_dict.items() if v}
    query_string = urlencode(filtered_query)

    return templates.TemplateResponse("report/error_report_list.html", {
        "request": request,
        "reports": reports,
        "page": page,
        "total_pages": total_pages,
        "start_page": start_page,
        "end_page": end_page,
        "query_string": query_string
    })



@app.get("/log_reports", response_class=HTMLResponse)
def log_report_list(
    request: Request,
    page: int = 1,
    limit: int = 10,
    search: str = "",         # ✅ 추가
    manager: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    log_type: str = "",
    start_date: str = "",
    end_date: str = "",
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    query = db.query(LogReport)

    # ✅ 통합 검색어 조건 추가
    if search:
        query = query.filter(
            (LogReport.manager.contains(search)) |
            (LogReport.client_name.contains(search)) |
            (LogReport.system_name.contains(search)) |
            (LogReport.target_env.contains(search)) |
            (LogReport.log_type.contains(search)) |
            (LogReport.content.contains(search))
        )

    # ✅ 기존 필터 조건
    if manager:
        query = query.filter(LogReport.manager.contains(manager))
    if status:
        query = query.filter(LogReport.status == status)
    if client_name:
        query = query.filter(LogReport.client_name.contains(client_name))
    if system_name:
        query = query.filter(LogReport.system_name.contains(system_name))
    if target_env:
        query = query.filter(LogReport.target_env.contains(target_env))
    if log_type:
        query = query.filter(LogReport.log_type.contains(log_type))
    if start_date and end_date:
        query = query.filter(
            LogReport.log_date.between(start_date + " 00:00:00", end_date + " 23:59:59")
        )

    total = query.count()
    total_pages = ceil(total / limit)
    start_page = max(1, page - 2)
    end_page = min(start_page + 4, total_pages)
    start_page = max(1, end_page - 4)

    reports = query.order_by(LogReport.log_date.desc()).offset(offset).limit(limit).all()

    query_dict = {
        "search": search,
        "manager": manager,
        "status": status,
        "client_name": client_name,
        "system_name": system_name,
        "target_env": target_env,
        "log_type": log_type,
        "start_date": start_date,
        "end_date": end_date
    }
    filtered_query = {k: v for k, v in query_dict.items() if v}
    query_string = urlencode(filtered_query)

    return templates.TemplateResponse("report/log_reports.html", {
        "request": request,
        "reports": reports,
        "page": page,
        "total_pages": total_pages,
        "start_page": start_page,
        "end_page": end_page,
        "query_string": query_string
    })
