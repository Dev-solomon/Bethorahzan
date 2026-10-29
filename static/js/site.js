// Bethorahzan - lightweight progressive enhancement.
(function(){
  document.querySelectorAll('[data-confirm]').forEach(function(form){
    form.addEventListener('submit',function(e){if(!window.confirm(form.getAttribute('data-confirm')))e.preventDefault()})
  });
  var amount=document.getElementById('job-budget');
  if(amount){
    var total=document.getElementById('job-total'),worker=document.getElementById('job-worker'),fee=document.getElementById('job-fee');
    var update=function(){var cents=Math.round((Number(amount.value)||0)*100),feeCents=Math.round(cents*.1);var fmt=function(v){return '$'+(v/100).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})};total.textContent=fmt(cents);worker.textContent=fmt(cents-feeCents);fee.textContent=fmt(feeCents)};
    amount.addEventListener('input',update);update();
  }
  document.querySelectorAll('[data-donation-amount]').forEach(function(btn){btn.addEventListener('click',function(){document.getElementById('donation-amount').value=btn.dataset.donationAmount})});
})();
