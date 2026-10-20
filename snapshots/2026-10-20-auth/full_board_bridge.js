/* Isolated full-board synchronization experiment: server is authoritative. */
(()=>{
 let revisions=new Map(),ready=false,blocked=true,queue=Promise.resolve(),loading=true;
 const nativePersist=persist;
 const indicator=document.createElement('div');indicator.id='syncIndicator';indicator.style.cssText='position:fixed;bottom:8px;right:8px;background:#fff3cd;color:#513f00;padding:8px;z-index:9999;border:1px solid #cda';document.body.append(indicator);
 const status=t=>indicator.textContent='Тест синхронизации: '+t;
 const logoutButton=document.createElement('button');logoutButton.textContent='Выйти';logoutButton.style.position='fixed';logoutButton.style.right='8px';logoutButton.style.bottom='55px';logoutButton.style.zIndex='9999';document.body.append(logoutButton);
 logoutButton.onclick=async()=>{if(!ready||blocked||loading)return alert('Дождитесь сохранения');logoutButton.disabled=true;try{await queue;if(blocked)throw Error('Сохранение не завершено');const r=await fetch('/api/full/logout',{method:'POST'});if(!r.ok)throw Error('Ошибка выхода');location.reload()}catch(e){alert(e.message);logoutButton.disabled=false}};
 const snapshot=()=>({notes:JSON.parse(JSON.stringify(notes)),connections:JSON.parse(JSON.stringify(connections))});
 async function sync(bid,data){
  if(!ready||blocked||loading)return;
  const rev=revisions.get(bid);
  if(!rev){blocked=true;status('нет версии, запись остановлена');return}
  const r=await fetch('/api/full/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:bid,data,revision:rev})});
  const result=await r.json();
  if(r.status===409){blocked=true;status('КОНФЛИКТ: серверные данные сохранены');alert('Другое окно изменило доску. Сервер не перезаписан. Сохраните резервную копию и обновите страницу.');return}
  if(!r.ok){blocked=true;status('ошибка '+r.status+'; запись остановлена');return}
  revisions.set(bid,result.revision);status('сохранено');
 }
 function enqueue(){if(!ready||blocked||loading)return;const bid=activeBoard,data=snapshot();queue=queue.then(()=>sync(bid,data)).catch(e=>{blocked=true;status('ошибка сети: '+e.message)});return queue}
 persist=function(){if(loading||blocked)return;nativePersist();enqueue()};
 const nativeSave=save;
 save=async function(){if(!ready||blocked){alert('Сервер не готов, сохранение заблокировано');return}await nativeSave();enqueue()};
 const nativeSwitch=switchBoard;
 switchBoard=function(id){if(!ready||blocked){status('переключение заблокировано');return}if(!revisions.has(id)){status('доска не загружена');return}nativeSwitch(id)};
 createBoard=async function(){
  if(!ready||blocked)return alert('Сервер не готов');
  const name=prompt('Название новой доски:');if(!name||!name.trim())return;
  const label=name.trim().slice(0,70),id=crypto.randomUUID();
  try{
   await queue;
   const response=await fetch('/api/full/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,name:label})});
   const result=await response.json();if(!response.ok)throw Error(result.error||'HTTP '+response.status);
   revisions.set(id,result.revision);
   localStorage.setItem(noteKey(id),'[]');localStorage.setItem(linkKey(id),'[]');
   boards.push({id,name:label});localStorage.setItem(BOARD_LIST_KEY,JSON.stringify(boards));
   switchBoard(id);status('доска создана');
  }catch(e){alert('Не удалось создать доску: '+e.message)}
 };
 deleteCurrentBoard=function(){alert('Удаление досок на сервере пока не подключено')};
 (async()=>{
  try{
   status('загрузка данных с сервера');
   let r=await fetch('/api/full/boards',{cache:'no-store'});
   if(r.status===401){
    const overlay=document.createElement('div');overlay.style.cssText='position:fixed;inset:0;background:#172033e8;display:grid;place-items:center;z-index:99999';
    const form=document.createElement('form');form.style.cssText='background:white;padding:24px;border-radius:12px;max-width:350px;width:90%;display:grid;gap:12px';
    const heading=document.createElement('strong');heading.textContent='Создание аккаунта';
    const name=document.createElement('input');name.placeholder='Логин';name.required=true;name.autocomplete='username';
    const password=document.createElement('input');password.type='password';password.placeholder='ПИН-код (4 цифры)';password.required=true;password.autocomplete='current-password';password.inputMode='numeric';password.pattern='[0-9]{4}';password.minLength=4;password.maxLength=4;
    const button=document.createElement('button');button.type='submit';button.textContent='Создать аккаунт и войти';
    const register=document.createElement('button');register.type='button';register.textContent='У меня уже есть аккаунт';
    const hint=document.createElement('small');hint.textContent='Придумайте логин от 3 символов и ПИН из четырёх цифр. Только для локального теста.';
    const error=document.createElement('span');error.style.color='#a11';
    form.append(heading,name,password,hint,button,register,error);overlay.append(form);document.body.append(overlay);
    await new Promise(resolve=>{
     const submit=async mode=>{
      button.disabled=true;register.disabled=true;error.textContent='Проверка…';
      try{const response=await fetch('/api/full/'+mode,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name.value,password:password.value})});const result=await response.json();password.value='';if(!response.ok)throw Error(result.error||'Ошибка входа');overlay.remove();resolve()}catch(err){error.textContent=err.message}finally{button.disabled=false;register.disabled=false}
     };
     let mode='register';
     form.addEventListener('submit',e=>{e.preventDefault();if(form.reportValidity())submit(mode)});
     register.addEventListener('click',()=>{mode=mode==='register'?'login':'register';heading.textContent=mode==='register'?'Создание аккаунта':'Вход в аккаунт';button.textContent=mode==='register'?'Создать аккаунт и войти':'Войти';register.textContent=mode==='register'?'У меня уже есть аккаунт':'Создать новый аккаунт';error.textContent='';});
    });
    r=await fetch('/api/full/boards',{cache:'no-store'});
   }
   if(!r.ok)throw Error('HTTP '+r.status);
   const result=await r.json(),main=result.boards.find(b=>b.id==='main');if(!main)throw Error('Главная доска не найдена');
   if(!Array.isArray(main.data.notes)||!Array.isArray(main.data.connections))throw Error('Неверный формат');
   boards=result.boards.map(b=>({id:b.id,name:b.id==='main'?'Моя доска':(JSON.parse(localStorage.getItem(BOARD_LIST_KEY)||'[]').find(x=>x.id===b.id)?.name||'Доска')}));
   for(const b of result.boards){revisions.set(b.id,b.revision);localStorage.setItem(noteKey(b.id),JSON.stringify(b.data.notes));localStorage.setItem(linkKey(b.id),JSON.stringify(b.data.connections));}
   const remembered=localStorage.getItem(ACTIVE_BOARD_KEY);
   const initial=result.boards.find(b=>b.id===remembered)||main;
   activeBoard=initial.id;notes=initial.data.notes;connections=initial.data.connections;selected.clear();
   localStorage.setItem(BOARD_LIST_KEY,JSON.stringify(boards));localStorage.setItem(ACTIVE_BOARD_KEY,initial.id);
   nativePersist();refreshBoards();render();
   loading=false;blocked=false;ready=true;status('подключено, доска загружена');
  }catch(e){loading=false;blocked=true;status('ОШИБКА загрузки: '+e.message)}
 })();
})();