import {packing} from './shared-stations.mjs';
import {stationShift} from './station-shift.mjs';

export const render=context=>stationShift(context,'packing','Paketleme',packing(context.state,context.ui));
