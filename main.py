from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.oauth2.id_token
from google.auth.transport import requests
from google.cloud import firestore
from datetime import datetime

app = FastAPI()
firebase_request_adapter = requests.Request()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
db = firestore.Client()

# Helper Functions
async def verify_firebase_token(request: Request):
    token = request.cookies.get("token")
    if not token:
        return None
    try:
        decoded_token = google.oauth2.id_token.verify_firebase_token(token, firebase_request_adapter)
        return decoded_token
    except ValueError as e:
        print(f"Token verification failed: {str(e)}")
        return None

async def get_user_uid(request: Request):
    user = await verify_firebase_token(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return user['user_id']

async def is_board_member(user_uid: str, task_board_ref) -> bool:
    """Check if user is a member of the task board"""
    task_board = task_board_ref.get()
    return any(member.id == user_uid for member in task_board.to_dict().get("members", []))

async def is_board_creator(user_uid: str, task_board_ref) -> bool:
    """Check if user is the creator of the task board"""
    task_board = task_board_ref.get()
    return task_board.to_dict().get("created_by").id == user_uid

async def get_board_members(task_board_ref):
    """Get all members of a task board with their details"""
    task_board = task_board_ref.get()
    if not task_board.exists:
        return []  # Return an empty list if the task board does not exist
    members = []
    for member_ref in task_board.to_dict().get("members", []):
        member = member_ref.get()
        if member.exists:
            member_data = member.to_dict()
            members.append({
                "id": member_ref.id,
                "name": member_data.get("fullName", "Unknown User"),
                "email": member_data.get("email", "")
            })
    return members

async def get_available_users(user_uid: str, exclude_ids: list = None):
    """Get all users except current user and excluded IDs"""
    exclude_ids = exclude_ids or []
    users = []
    users_ref = db.collection("users")
    docs = users_ref.stream()
    for doc in docs:
        if doc.id != user_uid and doc.id not in exclude_ids:
            user_data = doc.to_dict()
            users.append({
                "id": doc.id,
                "name": user_data.get("fullName", "Unknown User"),
                "email": user_data.get("email", "")
            })
    return users

# Authentication Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# Board Routes
@app.get("/create-board", response_class=HTMLResponse)
async def create_board(request: Request):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    users = await get_available_users(user_uid)
    return templates.TemplateResponse("create_board.html", {
        "request": request,
        "users": users
    })

@app.post("/taskboards")
async def create_taskboard(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    users: list[str] = Form([])
):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    taskboard_ref = db.collection("task_boards").document()
    
    taskboard_ref.set({
        "name": name,
        "description": description,
        "created_by": db.collection("users").document(user_uid),
        "created_at": firestore.SERVER_TIMESTAMP,
        "members": [db.collection("users").document(user_uid)] + 
                   [db.collection("users").document(uid) for uid in users]
    })
    
    # Add reference to all members' taskboards
    member_ids = [user_uid] + users
    for member_id in member_ids:
        member_ref = db.collection("users").document(member_id)
        member_ref.update({"task_boards": firestore.ArrayUnion([taskboard_ref])})
    
    return RedirectResponse(url="/home", status_code=303)

@app.get("/task-board/{task_board_id}", response_class=HTMLResponse)
async def task_board(request: Request, task_board_id: str):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)
    
    # Verify access
    if not await is_board_member(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Access denied")
    
    task_board_data = task_board_ref.get().to_dict()
    members = await get_board_members(task_board_ref)
    is_creator = await is_board_creator(user_uid, task_board_ref)
    
    # Get tasks
    tasks = []
    tasks_query = task_board_ref.collection("tasks")
    for task_doc in tasks_query.stream():
        task_data = task_doc.to_dict()
        task_data['id'] = task_doc.id
        task_data['assigned_members'] = [m.id for m in task_data.get('assigned_members', [])]
        tasks.append(task_data)

    return templates.TemplateResponse("task_board.html", {
        "request": request,
        "task_board_name": task_board_data.get("name"),
        "task_board_id": task_board_id,
        "tasks": tasks,
        "members": members,
        "is_creator": is_creator,
        "user_uid": user_uid,
        "creator_id": task_board_data.get("created_by").id
    })

@app.get("/task-board/{task_board_id}/edit")
async def edit_task_board_page(request: Request, task_board_id: str):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)
    
    if not await is_board_creator(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Only the creator can edit this board")
    
    task_board_data = task_board_ref.get().to_dict()
    members = await get_board_members(task_board_ref)
    
    return templates.TemplateResponse("edit_board.html", {
        "request": request,
        "task_board": task_board_data,
        "task_board_id": task_board_id,
        "members": members
    })

@app.post("/task-board/{task_board_id}/update")
async def update_task_board(
    request: Request,
    task_board_id: str,
    name: str = Form(...),
    description: str = Form(...)
):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)
    
    if not await is_board_creator(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Only the creator can edit this board")
    
    task_board_ref.update({"name": name, "description": description})
    return RedirectResponse(url=f"/task-board/{task_board_id}", status_code=303)

@app.post("/task-board/{task_board_id}/delete")
async def delete_task_board(request: Request, task_board_id: str):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)
    
    if not await is_board_creator(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Only the creator can delete the board")
    
    # Check if board has any tasks
    tasks_query = task_board_ref.collection("tasks").limit(1)
    if len(list(tasks_query.stream())) > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete board with existing tasks. Please delete all tasks first."
        )
    
    # Get current members (excluding creator)
    members = await get_board_members(task_board_ref)
    if len(members) > 1:  # More than just the creator
        raise HTTPException(
            status_code=400,
            detail="Cannot delete board with members. Please remove all members first."
        )
    
    # Delete the board
    task_board_ref.delete()
    
    # Remove board reference from creator
    creator_ref = db.collection("users").document(user_uid)
    creator_ref.update({
        "task_boards": firestore.ArrayRemove([task_board_ref])
    })
    
    return {
        "status": "success",
        "message": "Board deleted successfully"
    }

# Member Management Routes
@app.post("/task-board/{task_board_id}/add-member")
async def add_board_member(request: Request, task_board_id: str):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)
    
    if not await is_board_creator(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Only the creator can add members")
    
    data = await request.json()
    member_id = data.get('user_id')
    member_ref = db.collection("users").document(member_id)
    
    if not member_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Add to board members
    task_board_ref.update({"members": firestore.ArrayUnion([member_ref])})
    member_ref.update({"task_boards": firestore.ArrayUnion([task_board_ref])})
    
    return {"status": "success"}

@app.post("/task-board/{task_board_id}/remove-member")
async def remove_board_member(request: Request, task_board_id: str):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)
    
    if not await is_board_creator(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Only the creator can remove members")
    
    data = await request.json()
    member_id = data.get('user_id')
    member_ref = db.collection("users").document(member_id)
    
    # Remove from board members
    task_board_ref.update({"members": firestore.ArrayRemove([member_ref])})
    
    # Remove board from member's task_boards
    member_ref.update({"task_boards": firestore.ArrayRemove([task_board_ref])})
    
    # Unassign from all tasks
    tasks_query = task_board_ref.collection("tasks")
    for task_doc in tasks_query.stream():
        task_data = task_doc.to_dict()
        if "assigned_members" in task_data:
            updated_assignments = [m for m in task_data["assigned_members"] if m.id != member_id]
            task_doc.reference.update({"assigned_members": updated_assignments})
    
    return {"status": "success"}

# Task Routes
@app.get("/task-board/{task_board_id}/add-task", response_class=HTMLResponse)
async def add_task_page(request: Request, task_board_id: str):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)
    
    if not await is_board_member(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Access denied")
    
    task_board_data = task_board_ref.get().to_dict()
    members = await get_board_members(task_board_ref)
    
    return templates.TemplateResponse("add_task.html", {
        "request": request,
        "task_board_name": task_board_data.get("name"),
        "task_board_id": task_board_id,
        "members": members
    })

@app.post("/task-board/{task_board_id}/tasks", response_class=HTMLResponse)
async def create_task(
    request: Request,
    task_board_id: str,
    title: str = Form(...),
    description: str = Form(...),
    deadline: str = Form(None),
    assigned_members: list[str] = Form([])
):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)

    if not await is_board_member(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check for existing tasks with the same title
    existing_tasks_query = task_board_ref.collection("tasks").where("title", "==", title)
    existing_tasks = existing_tasks_query.stream()

    if any(existing_tasks):
        task_board_data = task_board_ref.get().to_dict()
        members = await get_board_members(task_board_ref)
        return templates.TemplateResponse("add_task.html", {
            "request": request,
            "task_board_name": task_board_data.get("name"),
            "task_board_id": task_board_id,
            "members": members,
            "error": "A task with this name already exists."
        })

    task_data = {
        "title": title,
        "description": description,
        "status": "InComplete",
        "created_at": firestore.SERVER_TIMESTAMP,
        "created_by": db.collection("users").document(user_uid),
        "task_board": task_board_ref,
        "assigned_members": [db.collection("users").document(uid) for uid in assigned_members]
    }

    if deadline:
        task_data["deadline"] = datetime.strptime(deadline, "%Y-%m-%d")

    task_board_ref.collection("tasks").document().set(task_data)
    return RedirectResponse(url=f"/task-board/{task_board_id}", status_code=303)

@app.get("/task-board/{task_board_id}/tasks/{task_id}/edit")
async def edit_task_page(request: Request, task_board_id: str, task_id: str):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_ref = db.collection("task_boards").document(task_board_id).collection("tasks").document(task_id)
    task_data = task_ref.get().to_dict()
    
    if not await is_board_member(user_uid, task_data["task_board"]):
        raise HTTPException(status_code=403, detail="Access denied")
    
    members = await get_board_members(task_data["task_board"])
    
    return templates.TemplateResponse("edit_task.html", {
        "request": request,
        "task": {
            "id": task_id,
            "title": task_data.get("title"),
            "description": task_data.get("description"),
            "deadline": task_data.get("deadline"),
            "assigned_members": [m.id for m in task_data.get("assigned_members", [])],
            "task_board": {"id": task_board_id}
        },
        "members": members
    })

@app.post("/task-board/{task_board_id}/tasks/{task_id}/update")
async def update_task(
    request: Request,
    task_board_id: str,
    task_id: str,
    title: str = Form(...),
    description: str = Form(...),
    deadline: str = Form(None)
):
    form_data = await request.form()
    assigned_members = form_data.getlist("assigned_members")
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_ref = db.collection("task_boards").document(task_board_id).collection("tasks").document(task_id)
    task_data = task_ref.get().to_dict()

    if not await is_board_member(user_uid, task_data["task_board"]):
        raise HTTPException(status_code=403, detail="Access denied")

    parsed_deadline = None
    if deadline:
        try:
            parsed_deadline = datetime.strptime(deadline, "%Y-%m-%d")
        except ValueError:
            parsed_deadline = None
    members = await get_board_members(db.collection("task_boards").document(task_board_id))
    # 🔍 Check for duplicate title in the same task board
    tasks = db.collection("task_boards").document(task_board_id).collection("tasks").where("title", "==", title).stream()
    for t in tasks:
        if t.id != task_id:  # Skip if it's the same task
            return templates.TemplateResponse("edit_task.html", {
                "request": request,
                "task": {
                    "id": task_id,
                    "title": title,
                    "description": description,
                    "deadline": parsed_deadline,
                    "assigned_members": assigned_members,
                    "task_board": {"id": task_board_id}
                },
                "members": members,
                "error": "A task with this title already exists."
            })

    update_data = {
        "title": title,
        "description": description,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "assigned_members": [db.collection("users").document(uid) for uid in assigned_members],
        "status": "InComplete"
    }

    if deadline:
        update_data["deadline"] = datetime.strptime(deadline, "%Y-%m-%d")

    task_ref.update(update_data)
    return RedirectResponse(url=f"/task-board/{task_board_id}", status_code=303)


@app.post("/task-board/{task_board_id}/tasks/{task_id}/complete")
async def complete_task(request: Request, task_board_id: str, task_id: str):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_ref = db.collection("task_boards").document(task_board_id).collection("tasks").document(task_id)
    task_data = task_ref.get().to_dict()
    
    # Verify user is assigned to this task
    if user_uid not in [m.id for m in task_data.get('assigned_members', [])]:
        raise HTTPException(status_code=403, detail="Not assigned to this task")
    
    task_ref.update({
        "status": "completed",
        "completed_at": firestore.SERVER_TIMESTAMP
    })
    return {"status": "success"}

@app.post("/task-board/{task_board_id}/tasks/{task_id}/delete")
async def delete_task(request: Request, task_board_id: str, task_id: str):
    user_uid = await get_user_uid(request)
    task_ref = db.collection("task_boards").document(task_board_id).collection("tasks").document(task_id)
    task_data = task_ref.get().to_dict()
    
    if not await is_board_member(user_uid, task_data["task_board"]):
        raise HTTPException(status_code=403, detail="Access denied")
    
    task_ref.delete()
    return RedirectResponse(url=f"/task-board/{task_board_id}", status_code=303)

# User Routes
@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    user_ref = db.collection("users").document(user_uid)
    user_data = user_ref.get().to_dict()

    task_boards = []
    if "task_boards" in user_data:
        for board_ref in user_data["task_boards"]:
            board = board_ref.get()
            if board.exists:
                task_boards.append({
                    "id": board_ref.id,
                    "name": board.get("name"),
                    "description": board.get("description"),
                    "is_creator": board.get("created_by").id == user_uid
                })

    return templates.TemplateResponse("home.html", {
        "request": request,
        "username": user_data.get("fullName", "Unknown User"),
        "task_boards": task_boards
    })

@app.get("/api/users/search")
async def search_users(request: Request, q: str, board_id: str = None):
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    users_ref = db.collection("users")
    
    # Search by name and email
    name_query = users_ref.where("fullName", ">=", q).where("fullName", "<=", q + "\uf8ff")
    email_query = users_ref.where("email", ">=", q).where("email", "<=", q + "\uf8ff")
    
    # Get current board members if board_id provided
    current_members = set()
    if board_id:
        board_ref = db.collection("task_boards").document(board_id)
        board = board_ref.get()
        if board.exists:
            current_members = {m.id for m in board.to_dict().get("members", [])}
    
    # Combine and deduplicate results
    seen_ids = set()
    users = []
    
    for doc in name_query.stream():
        if doc.id != user_uid and doc.id not in seen_ids and doc.id not in current_members:
            seen_ids.add(doc.id)
            user_data = doc.to_dict()
            users.append({
                "id": doc.id,
                "name": user_data.get("fullName", "Unknown User"),
                "email": user_data.get("email", "")
            })
    
    for doc in email_query.stream():
        if doc.id != user_uid and doc.id not in seen_ids and doc.id not in current_members:
            seen_ids.add(doc.id)
            user_data = doc.to_dict()
            users.append({
                "id": doc.id,
                "name": user_data.get("fullName", "Unknown User"),
                "email": user_data.get("email", "")
            })
    
    return users

@app.post("/task-board/{task_board_id}/tasks/{task_id}/assign")
async def assign_task(
    request: Request,
    task_board_id: str,
    task_id: str
):
    """Assign members to a task."""
    user_uid = await get_user_uid(request)
    if isinstance(user_uid, RedirectResponse):
        return user_uid
    task_board_ref = db.collection("task_boards").document(task_board_id)
    task_ref = task_board_ref.collection("tasks").document(task_id)
    
    # Verify user has access to the board
    if not await is_board_member(user_uid, task_board_ref):
        raise HTTPException(status_code=403, detail="Access denied")
    
    data = await request.json()
    member_ids = data.get('member_ids', [])
    
    if not member_ids:
        raise HTTPException(status_code=400, detail="No members specified")
    
    # Verify all members belong to the board
    board_members = await get_board_members(task_board_ref)
    board_member_ids = {m['id'] for m in board_members}
    
    for member_id in member_ids:
        if member_id not in board_member_ids:
            raise HTTPException(
                status_code=400, 
                detail=f"User {member_id} is not a board member"
            )
    
    # Convert member IDs to user references
    user_refs = [db.collection("users").document(uid) for uid in member_ids]
    
    # Update task with new assigned members (replace existing ones)
    task_ref.update({
        "assigned_members": user_refs
    })
    
    return {"status": "success", "message": "Task assigned successfully"}
