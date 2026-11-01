"""Real-view export integrity and action/observation pairing, without hardware."""
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from docs.W9.d405.action_labels import follow_actions
from docs.W9.d405.capture_storage import write_image
from docs.W9.d405.export_real_hdf5 import export_episode
from docs.W9.d405.prepare import input_hashes

ROOT = Path(__file__).resolve().parents[1]


def fixture(tmp_path):
    ep = tmp_path/'영상1'
    (ep/'rgb').mkdir(parents=True)
    (ep/'metadata.json').write_text(json.dumps(dict(complete=True, robot=True, color='red')))
    (ep/'source.gcode').write_bytes((ROOT/'trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode').read_bytes())
    (ep/'reference.jsonl').write_bytes((ROOT/'docs/W6/poses/pickup-red-s2.jsonl').read_bytes())
    (ep/'robot.jsonl').write_text('{}\n')
    (ep/'color_profile.json').write_text(json.dumps(dict(format='w9-color/1', matrix=np.eye(3).tolist())))
    rows=[]
    for k, bgr in enumerate(([0,0,200], [200,0,0])):
        image = np.empty((20,30,3), np.uint8)
        image[:] = bgr
        name = f'rgb/{k}.png'
        write_image(ep/name, image)
        rows.append(dict(file=name, t_s=k*.05))
    (ep/'frames.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    states=np.zeros((17,9),np.float32)
    states[:,8]=1
    indices=np.repeat([0,1],8)
    aligned=dict(times=np.arange(17)*.05, positions=np.zeros((17,3)),
        quaternions_wxyz=np.tile([1.,0,0,0],(17,1)),robot_states=states,
        frame_indices=indices,frame_error_s=np.zeros(16),gripper_actions=np.r_[-np.ones(8),np.ones(8)])
    np.savez_compressed(ep/'aligned.npz',**aligned)
    (ep/'alignment_report.json').write_text(json.dumps(dict(input_sha256=input_hashes(ep),
        accepted_max_frame_ms=70,steps=16)))
    return ep,aligned


def labels(aligned, reference, scale):
    actions=np.zeros((16,7),np.float32)
    actions[:,0]=np.arange(16)/16
    actions[:,-1]=aligned['gripper_actions']
    return actions,np.zeros((16,2)),dict(method='test deterministic action labels')


def test_real_export_corrects_target_without_mutating_capture_and_pairs_images(tmp_path):
    ep,aligned=fixture(tmp_path)
    before={p.name:p.read_bytes() for p in ep.iterdir() if p.is_file()}
    result=export_episode(ep,tmp_path/'out','blue',True,action_generator=labels)
    with h5py.File(result['path'],'r') as f:
        demo=f['data/demo_0']
        assert f['data'].attrs['instruction']=='pick up the blue block on the table'
        assert demo.attrs['recorded_capture_color']=='red'
        assert demo.attrs['reviewed_target']=='blue'
        assert demo.attrs['observation_mode']=='wrist_only'
        assert demo['obs/agentview_rgb'].id==demo['obs/eye_in_hand_rgb'].id
        np.testing.assert_array_equal(demo['frame_indices'][:],aligned['frame_indices'])
        np.testing.assert_allclose(demo['timestamps'][:],aligned['times'][:-1])
        np.testing.assert_array_equal(demo['robot_states'][:],aligned['robot_states'][:-1])
        np.testing.assert_array_equal(demo['actions'][:,-1],aligned['gripper_actions'])
        np.testing.assert_allclose(demo['actions'][:,0],np.arange(16)/16)
        np.testing.assert_array_equal(demo['obs/eye_in_hand_rgb'][0,0,0],[200,0,0])
        np.testing.assert_array_equal(demo['obs/eye_in_hand_rgb'][-1,0,0],[0,0,200])
    assert {p.name:p.read_bytes() for p in ep.iterdir() if p.is_file()}==before


def test_export_requires_real_success_and_valid_source_hashes(tmp_path):
    ep,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='Review the real pickup'):
        export_episode(ep,tmp_path/'out','blue',action_generator=labels)
    with (ep/'robot.jsonl').open('a') as f:
        f.write(' ')
    with pytest.raises(ValueError,match='Capture inputs changed'):
        export_episode(ep,tmp_path/'out','blue',True,action_generator=labels)


def test_rerun_checks_png_content_and_never_overwrites(tmp_path):
    ep,_=fixture(tmp_path)
    result=export_episode(ep,tmp_path/'out','blue',True,action_generator=labels)
    path=Path(result['path'])
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        export_episode(ep,tmp_path/'out','blue',True,action_generator=labels)
    assert export_episode(ep,tmp_path/'out','blue',True,skip_existing=True,
                          action_generator=labels)['status']=='existing'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    (ep/'rgb/0.png').write_bytes(b'changed source image')
    with pytest.raises(ValueError,match='source PNG changed'):
        export_episode(ep,tmp_path/'out','blue',True,skip_existing=True,action_generator=labels)


def test_existing_partial_is_not_deleted_or_overwritten(tmp_path):
    ep,_=fixture(tmp_path)
    out=tmp_path/'out'
    out.mkdir()
    partial=out/'MIROBOT_video1_SCENE1_pick_up_the_blue_block_on_the_table_demo.hdf5.partial'
    partial.write_bytes(b'another interrupted export')
    with pytest.raises(FileExistsError):
        export_episode(ep,out,'blue',True,action_generator=labels)
    assert partial.read_bytes()==b'another interrupted export'


def test_action_labels_use_next_pose_and_current_gripper_without_timestep_shift():
    class Env:
        def reset(self):
            self.pos=np.zeros(3)
            return dict(robot0_eef_pos=self.pos.copy(),robot0_eef_quat=[0,0,0,1])
        def step(self, action):
            self.pos+=np.asarray(action[:3])*.05
            return dict(robot0_eef_pos=self.pos.copy(),robot0_eef_quat=[0,0,0,1]),0,False,{}
        def close(self):
            self.closed=True
    env=Env()
    positions=np.zeros((17,3)); positions[:,0]=np.arange(17)*.001
    grip=np.r_[-np.ones(8),np.ones(8)]
    aligned=dict(positions=positions,quaternions_wxyz=np.tile([1.,0,0,0],(17,1)),gripper_actions=grip)
    ref=dict(start_eef_pos=[0,0,0],start_eef_quat_xyzw=[0,0,0,1])
    actions,gaps,report=follow_actions(aligned,ref,.663,env_factory=lambda:env)
    np.testing.assert_allclose(actions[:,0],.02)
    np.testing.assert_array_equal(actions[:,6],grip)
    np.testing.assert_allclose(gaps,0,atol=1e-12)
    assert report['warmup_steps']==0 and env.closed


def test_translator_warmup_is_excluded_from_paired_training_actions():
    class Env:
        def reset(self):
            self.pos=np.zeros(3)
            self.step_actions=[]
            return dict(robot0_eef_pos=self.pos.copy(),robot0_eef_quat=[0,0,0,1])
        def step(self, action):
            self.step_actions.append(action)
            self.pos+=np.asarray(action[:3])*.05
            return dict(robot0_eef_pos=self.pos.copy(),robot0_eef_quat=[0,0,0,1]),0,False,{}
        def close(self):
            self.closed=True
    env=Env()
    positions=np.zeros((17,3)); positions[:,0]=.005+np.arange(17)*.001
    aligned=dict(positions=positions,quaternions_wxyz=np.tile([1.,0,0,0],(17,1)),
                 gripper_actions=-np.ones(16))
    ref=dict(start_eef_pos=[0,0,0],start_eef_quat_xyzw=[0,0,0,1])
    actions,gaps,report=follow_actions(aligned,ref,.663,env_factory=lambda:env)
    assert report['warmup_steps']==1
    assert len(env.step_actions)==17 and len(actions)==16
    assert env.step_actions[0][0]==pytest.approx(.1)
    np.testing.assert_allclose(actions[:,0],.02)
    np.testing.assert_allclose(gaps,0,atol=1e-12)
