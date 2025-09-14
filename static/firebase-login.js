'use strict';

// Import Firebase modules
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.4.0/firebase-app.js";
import { getAuth, createUserWithEmailAndPassword, signInWithEmailAndPassword, signOut } from "https://www.gstatic.com/firebasejs/11.4.0/firebase-auth.js";

// Firebase Configuration
const firebaseConfig = {
    apiKey: "",
    authDomain: "",
    projectId: "",
    storageBucket: "",
    messagingSenderId: "",
    appId: ""
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

// Initialize Firestore
import { getFirestore, doc, setDoc } from "https://www.gstatic.com/firebasejs/11.4.0/firebase-firestore.js";
const db = getFirestore(app);


// Handle Login
const loginButton = document.getElementById("login");
if (loginButton) {
    loginButton.addEventListener('click', function (event) {
        event.preventDefault();  // Prevent default form submission
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;

        signInWithEmailAndPassword(auth, email, password)
            .then((userCredential) => {
                const user = userCredential.user;
                console.log("Logged in");

                user.getIdToken().then((token) => {
                    document.cookie = `token=${token}; path=/; SameSite=Strict`;
                    window.location.href = "/home";
                }).catch(err => {
                    console.error("Error getting token:", err);
                });
            })
            .catch((error) => {
                console.log(error.code + error.message);
                const alertDiv = document.getElementById("alert");
                alertDiv.innerText = "Incorrect email or password. Please try again."; 
                alertDiv.style.display = "block"; 
            });
    });
}

// Handle Register
document.addEventListener("DOMContentLoaded", function() {
    const registerButton = document.getElementById("register-button");
    if (registerButton) {
        registerButton.addEventListener('click', function() {
            const getElement = id => document.getElementById(id);
            const elements = {
                fullName: getElement("full-name"),
                email: getElement("email"),
                password: getElement("password"),
                confirmPassword: getElement("confirm-password"),
                alert: getElement("alert"),
                status: getElement("status")
            };

            // Validate elements exist
            if (!elements.fullName || !elements.email || 
                !elements.password || !elements.confirmPassword || !elements.alert) {
                console.error("Missing form elements");
                return;
            }

            // Get and sanitize values
            const values = {
                fullName: elements.fullName.value.trim(),
                email: elements.email.value.trim(),
                password: elements.password.value,
                confirmPassword: elements.confirmPassword.value
            };

            // Validate inputs
            const validations = [
                [!values.fullName, "Full name is required"],
                [!values.email, "Email is required"],
                [!values.password, "Password is required"],
                [!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email), "Invalid email format"],
                [values.password.length < 6, "Password must be at least 6 characters"],
                [values.password !== values.confirmPassword, "Passwords do not match"]
            ];

            for (const [condition, message] of validations) {
                if (condition) {
                    elements.alert.textContent = message;
                    elements.alert.style.display = "block";
                    return;
                }
            }

            // Create user
            createUserWithEmailAndPassword(auth, values.email, values.password)
                .then((userCredential) => {
                    const userData = {
                        fullName: values.fullName,
                        email: values.email,
                        createdAt: new Date().toISOString(),
                    };
                    
                    // First try with setDoc
                    return setDoc(doc(db, "users", userCredential.user.uid), userData)
                        .catch(error => {
                            // Fallback to update if document exists
                            if (error.code === 'permission-denied') {
                                return updateDoc(doc(db, "users", userCredential.user.uid), userData);
                            }
                            throw error;
                        })
                        .then(() => {
                            if (elements.status) {
                                elements.status.textContent = "Registration successful!";
                            }
                            return userCredential.user.getIdToken();
                        })
                        .then((token) => {
                            document.cookie = "token=" + token + "; path=/; SameSite=Strict";
                            window.location.href = "/home";
                        });
                })
                .catch((error) => {
                    console.error("Registration error:", error);
                    if (elements.alert) {
                    if (error.code === 'auth/email-already-in-use') {
                        elements.alert.textContent = "Email already exists.";
                    } else if (error.code === 'permission-denied') {
                        elements.alert.textContent = "Registration error: Database permissions not configured";
                    } else {
                        elements.alert.textContent = "Registration error: " + error.message;
                    }
                    elements.alert.style.display = "block";
                    }
                    
                    // Delete the auth user if Firestore save failed
                    if (auth.currentUser) {
                        auth.currentUser.delete()
                            .then(() => console.log("Firebase Auth user deleted"))
                            .catch(err => console.error("Error deleting user:", err));
                    }
                });
        });
    }
});


// Handle Logout
document.addEventListener("DOMContentLoaded", function() {
    const logoutButton = document.getElementById("logout-link");
    if (logoutButton) {
        logoutButton.addEventListener("click", function() {
            signOut(auth)
                .then(() => {
                    document.cookie = "token=; path=/; SameSite=Strict";
                    window.location = "/";
                })
                .catch(console.error);
        });
    }
});
