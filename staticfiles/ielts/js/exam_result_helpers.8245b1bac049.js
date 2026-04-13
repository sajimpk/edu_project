document.addEventListener('DOMContentLoaded', function(){
  // Locator click highlighting
  document.querySelectorAll('.locator').forEach(function(el){
    el.style.cursor = 'pointer'
    el.addEventListener('click', function(){
      // toggle highlight
      el.classList.toggle('locator-highlight')
      // scroll into view
      el.scrollIntoView({behavior:'smooth', block:'center'})
    })
  })
})
