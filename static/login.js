// login.js

import { auth } from "./firebase.js";
import { signInWithEmailAndPassword } 
from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

window.login = function () {

  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  const role = document.getElementById("role").value;
  const errorBox = document.getElementById("errorBox");

  
  errorBox.classList.add("d-none");
  errorBox.innerText = "";

  if (!email || !password) {
    errorBox.classList.remove("d-none");
    errorBox.innerText = "Please fill all fields.";
    return;
  }

  signInWithEmailAndPassword(auth, email, password)
    .then((userCredential) => {

      // Role-based redirect
      if (role === "student") {
        window.location.href = "student-dashboard.html";
      } else {
        window.location.href = "teacher-dashboard.html";
      }

    })
    .catch((error) => {
      console.error(error);

      errorBox.classList.remove("d-none");

      switch (error.code) {
        case "auth/user-not-found":
          errorBox.innerText = "User not found.";
          break;
        case "auth/wrong-password":
          errorBox.innerText = "Incorrect password.";
          break;
        case "auth/invalid-email":
          errorBox.innerText = "Invalid email format.";
          break;
        default:
          errorBox.innerText = "Login failed. " + error.message;
      }
    });
};