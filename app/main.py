from fastapi import FastAPI, Form, Request, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.database import get_db
from app.models.models import Report, ErrorReport, MspReport, LogReport, User
from fastapi.templating import Jinja2Templates
from math import ceil
from datetime import datetime, timedelta
import io
import csv
from starlette.middleware.sessions import SessionMiddleware
from urllib.parse import urlencode
from natsort import natsorted
from sqlalchemy import text
import re
from fastapi.responses import JSONResponse
from collections import defaultdict




router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecret123")


app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(router)

@app.get("/", response_class=HTMLResponse)
def main_page(request: Request, db: Session = Depends(get_db)):
    msp_reports = db.query(MspReport).order_by(MspReport.request_date.desc()).limit(5).all()
    error_reports = db.query(ErrorReport).order_by(ErrorReport.error_start_date.desc()).limit(5).all()
    log_reports = db.query(LogReport).order_by(LogReport.log_date.desc()).limit(5).all()
    return templates.TemplateResponse("main.html", {
        "request": request,
        "msp_reports": msp_reports,
        "error_reports": error_reports,
        "log_reports": log_reports
    })

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
        request.session['name'] = user.name
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
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    request_datetime = datetime.strptime(f"{request_date} {request_time}", "%Y-%m-%d %H:%M")
    completed_datetime = None
    if completed_date and completed_time:
        completed_datetime = datetime.strptime(f"{completed_date} {completed_time}", "%Y-%m-%d %H:%M")

    report = Report(
        create_by=user_id,
        report_type="msp",
        created_at=datetime.now()
    )
    db.add(report)
    db.commit()
    db.refresh(report)

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
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    report = Report(
        create_by=user_id,
        report_type="error",
        created_at=datetime.now()
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    error_start_dt = datetime.strptime(f"{error_start_date} {start_time}", "%Y-%m-%d %H:%M") if error_start_date and start_time else None
    error_end_dt = datetime.strptime(f"{error_end_date} {end_time}", "%Y-%m-%d %H:%M") if error_end_date and end_time else None

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
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    log_datetime = datetime.strptime(f"{log_date} {log_time}", "%Y-%m-%d %H:%M")
    completed_datetime = datetime.strptime(f"{completed_date} {completed_time}", "%Y-%m-%d %H:%M") if completed_date and completed_time else None

    report = Report(
        create_by=user_id,
        report_type="log",
        created_at=datetime.now()
    )
    db.add(report)
    db.commit()
    db.refresh(report)

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


@app.get("/reports/download")
async def download_msp_csv(
    start_date: str = "",
    end_date: str = "",
    manager: str = "",
    requester: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    request_type: str = "",
    search: str = "",
    db: Session = Depends(get_db)
):
    query = db.query(MspReport)

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
    if search:
        query = query.filter(
            MspReport.client_name.contains(search) |
            MspReport.system_name.contains(search) |
            MspReport.manager.contains(search)
        )

    reports = query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "요청일자", "고객사", "시스템명", "대상 환경",
        "요청자", "요청유형", "요청내용", "참고사항",
        "담당자", "상태", "완료일자", "답변내용", "비고"
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
    bom = '\ufeff'
    return Response(
        content=bom + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=msp_reports.csv"}
    )





@app.get("/error_reports/download")
async def download_error_csv(
    start_date: str = "",
    end_date: str = "",
    manager: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    target_component: str = "",
    search: str = "",
    db: Session = Depends(get_db)
):
    query = db.query(ErrorReport)

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
        query = query.filter(ErrorReport.error_start_date.between(start_date + " 00:00:00", end_date + " 23:59:59"))
    if search:
        query = query.filter(
            ErrorReport.client_name.contains(search) |
            ErrorReport.system_name.contains(search) |
            ErrorReport.manager.contains(search)
        )

    reports = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "장애일자", "고객사", "시스템명", "대상 환경", "장애대상", "고객 영향",
        "장애내용", "장애원인", "조치내용", "담당자", "상태", "장애종료일자", "비고"
    ])

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
async def download_log_csv(
    start_date: str = "",
    end_date: str = "",
    manager: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    log_type: str = "",
    search: str = "",
    db: Session = Depends(get_db)
):
    query = db.query(LogReport)

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
        query = query.filter(LogReport.log_date.between(start_date + " 00:00:00", end_date + " 23:59:59"))
    if search:
        query = query.filter(
            LogReport.client_name.contains(search) |
            LogReport.system_name.contains(search) |
            LogReport.manager.contains(search)
        )

    reports = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "일자", "고객사", "시스템명", "대상 환경", "유형",
        "내용", "조치", "담당자", "상태", "완료일자", "요약", "비고"
    ])

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

from sqlalchemy import asc, desc  # 추가

def natural_keys(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', text)]

@app.get("/reports", response_class=HTMLResponse)
def report_list(
    request: Request,
    page: int = 1,
    limit: int = 10,
    manager: str = "",
    requester: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    request_type: str = "",
    start_date: str = "",
    end_date: str = "",
    search: str = "",
    sort: str = "request_date",
    direction: str = "desc",
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    query = db.query(MspReport)

    if requester:
        query = query.filter(MspReport.requester.contains(requester))
    if manager:
        query = query.filter(MspReport.manager.contains(manager))
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

    # ✅ 통합검색: 여러 필드에 OR 조건으로 적용
    from sqlalchemy import or_
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                MspReport.client_name.like(keyword),
                MspReport.system_name.like(keyword),
                MspReport.manager.like(keyword),
                MspReport.requester.like(keyword),
                MspReport.request_type.like(keyword),
                MspReport.request_content.like(keyword),
                MspReport.purpose.like(keyword),
                MspReport.response.like(keyword),
                MspReport.etc.like(keyword),
                MspReport.status.like(keyword)
            )
        )

    all_reports = query.all()

    # 자연 정렬
    natural_sort_fields = ["client_name", "system_name", "manager", "request_type", "status", "requester"]
    if sort in natural_sort_fields:
        all_reports.sort(key=lambda x: natural_keys(getattr(x, sort) or ""), reverse=(direction == "desc"))
    elif hasattr(MspReport, sort):
        all_reports.sort(key=lambda x: getattr(x, sort), reverse=(direction == "desc"))

    total = len(all_reports)
    total_pages = ceil(total / limit)
    start_page = max(1, page - 2)
    end_page = min(start_page + 4, total_pages)
    start_page = max(1, end_page - 4)

    reports = all_reports[offset:offset + limit]

    query_dict = {
        "manager": manager,
        "requester": requester,
        "status": status,
        "client_name": client_name,
        "system_name": system_name,
        "requester": requester,
        "target_env": target_env,
        "request_type": request_type,
        "start_date": start_date,
        "end_date": end_date,
        "search": search,
        "sort": sort,
        "direction": direction
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
        "query_string": query_string,
        "current_sort": sort,
        "current_direction": direction
    })






@app.get("/error_reports", response_class=HTMLResponse)
def error_report_list(
    request: Request,
    page: int = 1,
    limit: int = 10,
    manager: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    target_component: str = "",
    start_date: str = "",
    end_date: str = "",
    search: str = "",
    sort: str = "error_start_date",
    direction: str = "desc",
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    query = db.query(ErrorReport)

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

    # ✅ 통합검색
    from sqlalchemy import or_
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                ErrorReport.client_name.like(keyword),
                ErrorReport.system_name.like(keyword),
                ErrorReport.manager.like(keyword),
                ErrorReport.status.like(keyword),
                ErrorReport.target_env.like(keyword),
                ErrorReport.target_component.like(keyword),
                ErrorReport.customer_impact.like(keyword),
                ErrorReport.error_info.like(keyword),
                ErrorReport.error_reason.like(keyword),
                ErrorReport.action_taken.like(keyword),
                ErrorReport.etc.like(keyword)
            )
        )

    all_reports = query.all()
    if sort in ["client_name", "system_name", "manager"]:
        all_reports.sort(key=lambda x: natural_keys(getattr(x, sort) or ""), reverse=(direction == "desc"))
    elif hasattr(ErrorReport, sort):
        all_reports.sort(key=lambda x: getattr(x, sort), reverse=(direction == "desc"))

    total = len(all_reports)
    total_pages = ceil(total / limit)
    start_page = max(1, page - 2)
    end_page = min(start_page + 4, total_pages)
    start_page = max(1, end_page - 4)

    reports = all_reports[offset:offset + limit]

    query_dict = {
        "manager": manager,
        "status": status,
        "client_name": client_name,
        "system_name": system_name,
        "target_env": target_env,
        "target_component": target_component,
        "start_date": start_date,
        "end_date": end_date,
        "search": search,
        "sort": sort,
        "direction": direction
    }
    query_string = urlencode({k: v for k, v in query_dict.items() if v})

    return templates.TemplateResponse("report/error_report_list.html", {
        "request": request,
        "reports": reports,
        "page": page,
        "total_pages": total_pages,
        "start_page": start_page,
        "end_page": end_page,
        "query_string": query_string,
        "current_sort": sort,
        "current_direction": direction
    })





@app.get("/log_reports", response_class=HTMLResponse)
def log_report_list(
    request: Request,
    page: int = 1,
    limit: int = 10,
    manager: str = "",
    status: str = "",
    client_name: str = "",
    system_name: str = "",
    target_env: str = "",
    log_type: str = "",
    start_date: str = "",
    end_date: str = "",
    search: str = "",
    sort: str = "log_date",
    direction: str = "desc",
    db: Session = Depends(get_db)
):
    offset = (page - 1) * limit
    query = db.query(LogReport)

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

    # ✅ 통합검색
    from sqlalchemy import or_
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                LogReport.client_name.like(keyword),
                LogReport.system_name.like(keyword),
                LogReport.manager.like(keyword),
                LogReport.status.like(keyword),
                LogReport.target_env.like(keyword),
                LogReport.log_type.like(keyword),
                LogReport.content.like(keyword),
                LogReport.action.like(keyword),
                LogReport.summary.like(keyword),
                LogReport.etc.like(keyword)
            )
        )

    all_reports = query.all()
    if sort in ["client_name", "system_name", "manager"]:
        all_reports.sort(key=lambda x: natural_keys(getattr(x, sort) or ""), reverse=(direction == "desc"))
    elif hasattr(LogReport, sort):
        all_reports.sort(key=lambda x: getattr(x, sort), reverse=(direction == "desc"))

    total = len(all_reports)
    total_pages = ceil(total / limit)
    start_page = max(1, page - 2)
    end_page = min(start_page + 4, total_pages)
    start_page = max(1, end_page - 4)

    reports = all_reports[offset:offset + limit]

    query_dict = {
        "manager": manager,
        "status": status,
        "client_name": client_name,
        "system_name": system_name,
        "target_env": target_env,
        "log_type": log_type,
        "start_date": start_date,
        "end_date": end_date,
        "search": search,
        "sort": sort,
        "direction": direction
    }
    query_string = urlencode({k: v for k, v in query_dict.items() if v})

    return templates.TemplateResponse("report/log_reports.html", {
        "request": request,
        "reports": reports,
        "page": page,
        "total_pages": total_pages,
        "start_page": start_page,
        "end_page": end_page,
        "query_string": query_string,
        "current_sort": sort,
        "current_direction": direction
    })



@app.get("/admin/users", response_class=HTMLResponse)
def user_management_page(request: Request, db: Session = Depends(get_db)):
    if request.session.get("username") != "admin":
        return RedirectResponse(url="/login", status_code=303)
    
    from sqlalchemy.orm import joinedload
    users = db.query(User).options(joinedload(User.clients)).all()
    return templates.TemplateResponse("admin/user_list.html", {
        "request": request,
        "users": users
    })

@app.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
def edit_user_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    if request.session.get("username") != "admin":
        return RedirectResponse(url="/login", status_code=303)
    
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return templates.TemplateResponse("admin/user_edit.html", {
        "request": request,
        "user": user
    })


@app.post("/admin/users/{user_id}/edit")
async def update_user_info(
    user_id: int,
    username: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.username = username
    user.name = name
    user.email = email
    db.commit()

    return RedirectResponse(url="/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/delete")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)



@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    user = db.query(User).filter(User.user_id == user_id).first()
    return templates.TemplateResponse("user/profile.html", {"request": request, "user": user})


@app.get("/change_password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("user/change_password.html", {"request": request, "error": None})


@app.post("/change_password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    user = db.query(User).filter(User.user_id == user_id).first()

    if not user or user.password != current_password:
        return templates.TemplateResponse("user/change_password.html", {
            "request": request,
            "error": "현재 비밀번호가 일치하지 않습니다."
        })

    if new_password != confirm_password:
        return templates.TemplateResponse("user/change_password.html", {
            "request": request,
            "error": "새 비밀번호가 일치하지 않습니다."
        })

    user.password = new_password
    db.commit()

    return RedirectResponse(url="/myinfo", status_code=303)


@app.get("/admin/stats", response_class=HTMLResponse)
def admin_stats(request: Request, db: Session = Depends(get_db)):
    if request.session.get("username") != "admin":
        return RedirectResponse(url="/login", status_code=303)

    total_reports = db.query(Report).count()
    last_7_days = datetime.today() - timedelta(days=7)
    last_30_days = datetime.today() - timedelta(days=30)
    recent_7 = db.query(Report).filter(Report.created_at >= last_7_days).count()
    recent_30 = db.query(Report).filter(Report.created_at >= last_30_days).count()

    # 상태 분포
    status_counts = defaultdict(int)
    for model in [MspReport, ErrorReport, LogReport]:
        for row in db.query(model.status).all():
            status_counts[row[0]] += 1

    # 기업별 리포트 개수
    client_summary = defaultdict(lambda: {"msp": 0, "error": 0, "log": 0})
    for row in db.query(MspReport.client_name).all():
        client_summary[row[0]]["msp"] += 1
    for row in db.query(ErrorReport.client_name).all():
        client_summary[row[0]]["error"] += 1
    for row in db.query(LogReport.client_name).all():
        client_summary[row[0]]["log"] += 1

    # 담당자별 처리 현황
    manager_counts = defaultdict(lambda: {"count": 0, "done": 0})
    for model in [MspReport, ErrorReport, LogReport]:
        for row in db.query(model.manager, model.status).all():
            manager_counts[row[0]]["count"] += 1
            if row[1] == "완료":
                manager_counts[row[0]]["done"] += 1

    # 시스템별 리포트 수
    system_counts = defaultdict(int)
    for model in [MspReport, ErrorReport, LogReport]:
        for row in db.query(model.system_name).all():
            system_counts[row[0]] += 1

    # ✅ 월별 리포트 수 (msp: request_date, error: error_start_date, log: log_date)
    from sqlalchemy import extract, func
    monthly_counts = defaultdict(lambda: {"msp": 0, "error": 0, "log": 0})

    for year, month, count in db.query(
        extract('year', MspReport.request_date),
        extract('month', MspReport.request_date),
        func.count()
    ).group_by(
        extract('year', MspReport.request_date),
        extract('month', MspReport.request_date)
    ).all():
        key = f"{int(year):04d}-{int(month):02d}"
        monthly_counts[key]["msp"] += count

    for year, month, count in db.query(
        extract('year', ErrorReport.error_start_date),
        extract('month', ErrorReport.error_start_date),
        func.count()
    ).group_by(
        extract('year', ErrorReport.error_start_date),
        extract('month', ErrorReport.error_start_date)
    ).all():
        key = f"{int(year):04d}-{int(month):02d}"
        monthly_counts[key]["error"] += count

    for year, month, count in db.query(
        extract('year', LogReport.log_date),
        extract('month', LogReport.log_date),
        func.count()
    ).group_by(
        extract('year', LogReport.log_date),
        extract('month', LogReport.log_date)
    ).all():
        key = f"{int(year):04d}-{int(month):02d}"
        monthly_counts[key]["log"] += count

    return templates.TemplateResponse("admin/stats.html", {
        "request": request,
        "total_reports": total_reports,
        "recent_7": recent_7,
        "recent_30": recent_30,
        "status_counts": dict(status_counts),
        "client_summary": dict(client_summary),
        "manager_counts": dict(manager_counts),
        "system_counts": dict(system_counts),
        "monthly_counts": dict(sorted(monthly_counts.items()))
    })
