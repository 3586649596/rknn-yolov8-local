import os

RKNNLite = False
try:
    from rknn.api import RKNN
except ImportError:
    print('import rknn failed,try to import rknnlite')
    RKNNLite = True
    from rknnlite.api import RKNNLite as RKNN


class RKNN_model_container():
    def __init__(self, model_path, target=None, device_id=None) -> None:
        rknn = RKNN()

        # Direct Load RKNN Model
        rknn.load_rknn(model_path)

        print('--> Init runtime environment')
        if RKNNLite or target==None:
            # Use all NPU cores by default on RKNNLite if available.
            # You can override with env: RKNN_NPU_CORE_MASK=0|1|2|0_1_2|auto
            core_mask_spec = os.environ.get('RKNN_NPU_CORE_MASK', '0_1_2').lower()
            core_mask = None
            if core_mask_spec in ('auto', '', 'none'):
                core_mask = None
            elif core_mask_spec == '0' and hasattr(rknn, 'NPU_CORE_0'):
                core_mask = rknn.NPU_CORE_0
            elif core_mask_spec == '1' and hasattr(rknn, 'NPU_CORE_1'):
                core_mask = rknn.NPU_CORE_1
            elif core_mask_spec == '2' and hasattr(rknn, 'NPU_CORE_2'):
                core_mask = rknn.NPU_CORE_2
            elif core_mask_spec == '0_1_2' and hasattr(rknn, 'NPU_CORE_0_1_2'):
                core_mask = rknn.NPU_CORE_0_1_2

            if core_mask is not None:
                print(f'  using RKNNLite core_mask={core_mask_spec}')
                try:
                    ret = rknn.init_runtime(core_mask=core_mask)
                except TypeError:
                    # Some runtime builds may not accept core_mask kwarg.
                    print('  core_mask init not supported, fallback to default init')
                    ret = rknn.init_runtime()
            else:
                if core_mask_spec not in ('auto', '', 'none'):
                    print(f'  unknown/unsupported core_mask={core_mask_spec}, fallback to default init')
                ret = rknn.init_runtime()
        else:
            ret = rknn.init_runtime(target=target, device_id=device_id)
        if ret != 0:
            print('Init runtime environment failed')
            exit(ret)
        print('done')
        
        self.rknn = rknn 

    def run(self, inputs):
        if isinstance(inputs, list) or isinstance(inputs, tuple):
            pass
        else:
            inputs = [inputs]

        result = self.rknn.inference(inputs=inputs)
    
        return result
