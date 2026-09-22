<?php
declare(strict_types=1);
foreach (['SessionPolicy', 'AuthStore'] as $name) { require __DIR__ . '/../src/' . $name . '.php'; }
use LaBookGateway\AuthStore;
use LaBookGateway\SessionPolicy;
$checks=0;
function check(bool $ok): void { global $checks; ++$checks; if (!$ok) { throw new RuntimeException('Auth store test failed: '.$checks); } }
function rejected(callable $fn, string $reason): void {
    try { $fn(); } catch (RuntimeException $e) { check($e->getMessage()===$reason); return; } check(false);
}
$now=2000000000;
$c=['public_origin'=>'https://public.example','expected_team_id'=>'TTEST','session_generation'=>'oauth-30', 'revoked_subjects'=>[]];
$policy=new SessionPolicy($c);
$identity=['team_id'=>'TTEST','user_id'=>'UTEST','workspace_checked'=>true,'verified_at'=>$now,
    'email'=>'not-stored@example.invalid','access_token'=>'not-stored'];
$directory=sys_get_temp_dir().'/labook-auth-'.bin2hex(random_bytes(8)); mkdir($directory,0700);
try {
    $store=new AuthStore($directory.'/auth.sqlite');
    $db=new PDO('sqlite:'.$directory.'/auth.sqlite');
    foreach ([['workspace_checked'=>false],['team_id'=>'TOTHER'],['verified_at'=>$now-61]] as $change) {
        rejected(fn()=>$store->establish(array_replace($identity,$change),'',$policy,$now),'identity_rejected');
    }
    check((int)$db->query('SELECT COUNT(*) FROM auth_users')->fetchColumn()===0);
    $first=$store->establish($identity,'',$policy,$now);
    check(strlen($first['token'])===64 && $first['expires_at']===$now+30*86400);
    $row=$db->query('SELECT * FROM auth_sessions')->fetch(PDO::FETCH_ASSOC);
    check($row['session_hash']===hash('sha256',$first['token']));
    check(!str_contains(json_encode($row),'not-stored'));
    check($store->session($first['token'],$policy,$now+1)['subject']==='slack:TTEST:UTEST');
    rejected(fn()=>$store->session(str_repeat('0',64),$policy,$now+1),'login_required');
    rejected(fn()=>$store->session('invalid',$policy,$now+1),'login_required');
    foreach ([['session_generation'=>'changed'],['expected_team_id'=>'TOTHER'],['revoked_subjects'=>['slack:TTEST:UTEST']]] as $change) {
        $different=new SessionPolicy(array_replace($c,$change));
        rejected(fn()=>$store->session($first['token'],$different,$now+2),'login_required');
    }
    // Re-login rotates the opaque ID and CSRF, reuses the identity row, and revokes the prior session.
    $second=$store->establish($identity,$first['token'],$policy,$now+3);
    check($second['token']!==$first['token']);
    check($store->session($second['token'],$policy,$now+3)['csrf']!==$row['csrf']);
    check((int)$db->query('SELECT COUNT(*) FROM auth_users')->fetchColumn()===1);
    rejected(fn()=>$store->session($first['token'],$policy,$now+3),'login_required');
    check($store->session($second['token'],$policy,$now+3+30*86400-1)['subject']==='slack:TTEST:UTEST');
    check((int)$db->query('SELECT expires_at FROM auth_sessions WHERE revoked_at IS NULL')->fetchColumn()===$now+3+30*86400);
    rejected(fn()=>$store->session($second['token'],$policy,$now+3+30*86400),'login_required');
    // A fresh fixture login also verifies logout/revocation without moving its clock backwards.
    $third=$store->establish($identity,'',$policy,$now+4);
    check($store->session($third['token'],$policy,$now+4)['subject']==='slack:TTEST:UTEST');
    $store->revoke($third['token'],$now+5);
    rejected(fn()=>$store->session($third['token'],$policy,$now+5),'login_required');
    $identity['user_id']='UOTHER';
    $other=$store->establish($identity,'',$policy,$now+6);
    check($store->session($other['token'],$policy,$now+6)['subject']==='slack:TTEST:UOTHER');
    check((int)$db->query('SELECT COUNT(*) FROM auth_users')->fetchColumn()===2);
} finally {
    unset($store,$db); foreach(glob($directory.'/*') as $file){unlink($file);} rmdir($directory);
}
echo json_encode(['checks'=>$checks,'status'=>'passed'])."\n";
