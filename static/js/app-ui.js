(function(){
  function ready(fn){
    if(document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function(){
    var splash = document.querySelector('.app-splash');
    if(splash){
      window.setTimeout(function(){ splash.classList.add('hide'); }, 3000);
      window.setTimeout(function(){ splash.remove(); }, 3400);
    }

    document.querySelectorAll('a[href]').forEach(function(link){
      var href = link.getAttribute('href') || '';
      if(href.startsWith('#') || href.startsWith('javascript:') || link.target === '_blank' || link.hasAttribute('download')) return;
      link.addEventListener('click', function(){ document.body.classList.add('is-leaving'); });
    });

    document.querySelectorAll('button,.btn,.btn-main,.btn-light,.admin-btn,.action-btn').forEach(function(el){
      el.addEventListener('pointerdown', function(){ el.classList.add('is-pressed'); });
      el.addEventListener('pointerup', function(){ el.classList.remove('is-pressed'); });
      el.addEventListener('pointerleave', function(){ el.classList.remove('is-pressed'); });
    });

    document.querySelectorAll('form').forEach(function(form){
      form.addEventListener('submit', function(){
        var submit = form.querySelector('button[type="submit"],input[type="submit"]');
        if(submit && !submit.dataset.keepText){
          submit.dataset.originalText = submit.value || submit.textContent;
          if(submit.tagName === 'INPUT') submit.value = 'Please wait...';
          else submit.textContent = 'Please wait...';
          submit.style.opacity = '.78';
        }
      });
    });

    var path = window.location.pathname;
    document.querySelectorAll('.app-bottom-nav a').forEach(function(a){
      var href = a.getAttribute('href') || '';
      try{
        if(href && path === new URL(href, window.location.origin).pathname){ a.classList.add('is-active'); }
      }catch(e){}
    });
  });
})();
