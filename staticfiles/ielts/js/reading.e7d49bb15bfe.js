(function(){
  // Minimal safe JS for timer, autosave, zoom and notes
  function $all(s){return Array.from(document.querySelectorAll(s))}

  // Default duration (minutes) can be provided via a meta tag named ielts-duration
  let durationSeconds = 60*60; // default 60 min
  const metaDuration = document.querySelector('meta[name="ielts-duration"]')
  if(metaDuration){
    const m = parseInt(metaDuration.getAttribute('content'))
    if(!isNaN(m)) durationSeconds = m*60
  }

  function formatTime(s){
    const mm = Math.floor(s/60).toString().padStart(2,'0')
    const ss = (s%60).toString().padStart(2,'0')
    return mm+':'+ss
  }

  const timerEl = document.getElementById('timer')
  const form = document.getElementById('reading-form')
  let remaining = durationSeconds
  if(timerEl){
    timerEl.textContent = formatTime(remaining)
    const iv = setInterval(()=>{
      remaining -= 1
      if(remaining<=0){
        timerEl.textContent = '00:00'
        clearInterval(iv)
        if(form) form.submit()
      } else {
        timerEl.textContent = formatTime(remaining)
      }
    },1000)
  }

  function saveAnswer(testId, questionId, selectedChoice, answerText){
    const data = new FormData()
    data.append('test_id', testId)
    data.append('question_id', questionId)
    if(selectedChoice) data.append('selected_choice', selectedChoice)
    if(answerText) data.append('answer_text', answerText)
    const csrftokenEl = document.querySelector('[name=csrfmiddlewaretoken]')
    const csrftoken = csrftokenEl? csrftokenEl.value : ''
    fetch('/ielts/save-answer/', {method:'POST', body:data, headers:{'X-CSRFToken': csrftoken}}).catch(()=>{})
  }

  $all('.save-answer').forEach(el=>{
    el.addEventListener('change', function(e){
      const testId = this.dataset.testId
      const qid = this.dataset.questionId
      const val = this.value
      saveAnswer(testId, qid, val, '')
    })
  })

  $all('.save-answer-text').forEach(el=>{
    el.addEventListener('blur', function(e){
      const testId = this.dataset.testId
      const qid = this.dataset.questionId
      saveAnswer(testId, qid, '', this.value)
    })
  })

  // Zoom controls
  const zoomIn = document.getElementById('zoom-in')
  const zoomOut = document.getElementById('zoom-out')
  const passages = document.getElementById('passages')
  let fontSize = 16
  if(zoomIn) zoomIn.addEventListener('click', ()=>{fontSize+=2; if(passages) passages.style.fontSize = fontSize+'px'})
  if(zoomOut) zoomOut.addEventListener('click', ()=>{fontSize=Math.max(12,fontSize-2); if(passages) passages.style.fontSize = fontSize+'px'})

  // Notes: capture selection and store in localStorage
  document.addEventListener('mouseup', function(e){
    const sel = window.getSelection()
    if(sel && sel.toString().trim()){
      const text = sel.toString()
      const note = prompt('Add note for selected text:', '')
      if(note!==null){
        const key = 'ielts_notes_' + (document.location.pathname || '')
        const store = JSON.parse(localStorage.getItem(key) || '[]')
        store.push({text: text, note: note, at: Date.now()})
        localStorage.setItem(key, JSON.stringify(store))
        alert('Note saved — open Notes to view')
      }
      sel.removeAllRanges()
    }
  })

  const notesBtn = document.getElementById('show-notes')
  const notesPanel = document.getElementById('notes-panel')
  if(notesBtn && notesPanel){
    notesBtn.addEventListener('click', function(){
      const key = 'ielts_notes_' + (document.location.pathname || '')
      const store = JSON.parse(localStorage.getItem(key) || '[]')
      notesPanel.style.display = notesPanel.style.display === 'none' ? 'block' : 'none'
      notesPanel.innerHTML = '<h6>Notes</h6>' + (store.length? store.map(n=>'<div class="note-item"><strong>'+n.text+'</strong><div>'+n.note+'</div></div>').join('') : '<div class="text-muted">No notes</div>')
    })
  }

})();
