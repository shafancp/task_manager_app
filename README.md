# 📝 Task Management System (FastAPI + Firebase)

A task management web application built with **FastAPI** and **Firebase (Firestore + Authentication)**.  
This system allows users to create and manage task boards, add members, assign tasks, and collaborate efficiently.  

---

## 🚀 Features

- 🔑 **Authentication**
  - Firebase-based user authentication (registration, login).
  - Token validation using cookies.

- 📋 **Task Boards**
  - Create, update, and delete task boards.
  - Add/remove board members.
  - Role-based access:
    - **Creator**: Full control (edit/delete board, manage members).
    - **Member**: View and interact with assigned tasks.

- ✅ **Tasks**
  - Create, edit, assign, and delete tasks.
  - Mark tasks as completed (only by assigned members).
  - Prevent duplicate task titles in a board.
  - Deadlines and timestamps for tracking.

- 🔍 **Search**
  - Search users by name or email.
  - Exclude already added members.

- 🏠 **Home Dashboard**
  - Displays all task boards a user belongs to.
  - Highlights boards created by the user.

---

## 📂 Database Structure (Firestore)

### **Users Collection**
- `fullName`: Full name of the user  
- `email`: User email  
- `task_boards`: References to task boards the user is part of  
- `createdAt`: Timestamp of creation  

### **Task Boards Collection**
- `name`: Task board name  
- `description`: Task board description  
- `created_by`: Reference to creator (user)  
- `members`: List of user references in the board  
- `created_at`: Timestamp  

#### **Tasks Subcollection (per Task Board)**
- `title`: Task title  
- `description`: Task details  
- `status`: `"Incomplete"` | `"Completed"`  
- `deadline`: Optional deadline  
- `created_at`: Creation timestamp  
- `updated_at`: Last update timestamp  
- `created_by`: Reference to task creator  
- `assigned_members`: List of assigned user references  
- `completed_at`: Timestamp when completed  

---

## ⚙️ Key API Functions

### **Authentication & User Management**
- `verify_firebase_token(request)` → Validates Firebase token from cookies.  
- `get_user_uid(request)` → Returns UID of logged-in user.  
- `get_available_users(user_uid, exclude_ids)` → Fetch users excluding self/board members.  

### **Board Management**
- `create_taskboard(request, name, description, users)` → Create new board.  
- `update_task_board(request, task_board_id, name, description)` → Update board (creator only).  
- `delete_task_board(request, task_board_id)` → Delete board if no tasks/members remain.  
- `add_board_member(request, task_board_id)` → Add user to board (creator only).  
- `remove_board_member(request, task_board_id)` → Remove user & unassign from tasks (creator only).  

### **Task Management**
- `create_task(request, task_board_id, title, description, deadline, assigned_members)`  
- `update_task(request, task_board_id, task_id, title, description, deadline)`  
- `complete_task(request, task_board_id, task_id)` → Mark as completed (assigned only).  
- `delete_task(request, task_board_id, task_id)`  

---

## 🛠️ Tech Stack
- **Backend**: [FastAPI](https://fastapi.tiangolo.com/)  
- **Database**: Firebase Firestore  
- **Auth**: Firebase Authentication  
- **Frontend Templates**: Jinja2 (via FastAPI)  

---

