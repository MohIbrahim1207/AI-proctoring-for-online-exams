// take_exam.js - show one question at a time

const questionCards = Array.from(document.querySelectorAll('.question-card'));
let currentIndex = 0;

function showIndex(i){
  questionCards.forEach((c, idx) => {
    c.style.display = idx === i ? 'block' : 'none';
  });
  document.getElementById('qIndex').innerText = `${i+1} / ${questionCards.length}`;
}

function nextQuestion(){
  if (currentIndex < questionCards.length - 1){
    currentIndex++;
    showIndex(currentIndex);
  }
}
function prevQuestion(){
  if (currentIndex > 0){
    currentIndex--;
    showIndex(currentIndex);
  }
}

window.nextQuestion = nextQuestion;
window.prevQuestion = prevQuestion;

// init
if (questionCards.length > 0){
  showIndex(0);
}

export {};
