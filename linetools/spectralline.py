"""
#;+ 
#; NAME:
#; spectralline
#;    Version 1.0
#;
#; PURPOSE:
#;    Module for SpectralLine class
#;   23-Jun-2015 by JXP
#;-
#;------------------------------------------------------------------------------
"""
from __future__ import print_function, absolute_import, division, unicode_literals

import numpy as np
from abc import ABCMeta, abstractmethod

from astropy import constants as const
from astropy import units as u
from astropy.units import Quantity

from linetools.spectra import io as lsio
from linetools.lists.linelist import LineList

#import xastropy.atomic as xatom
#from xastropy.stats import basic as xsb
#from xastropy.xutils import xdebug as xdb

# class SpectralLine(object):
# class AbsLine(SpectralLine):

# Class for Spectral line
class SpectralLine(object):
    """Class for a spectral line.  Emission or absorption 

    Attributes:
        ltype: str
          type of line, e.g.  Abs, Emiss
        wrest : Quantity
          Rest wavelength
    """
    __metaclass__ = ABCMeta

    # Initialize with wavelength
    def __init__(self, ltype, trans, linelist=None):
        """  Initiator

        Parameters
        ----------
        ltype : string
          Type of Spectral line, (Abs
        trans: Quantity or str
          Quantity: Rest wavelength (e.g. 1215.6700*u.AA)
          str: Name of transition (e.g. 'CIV 1548')
        linelist : LineList, optional
          Class of linelist or str setting LineList
        """

        # Required
        self.ltype = ltype
        if ltype not in ['Abs']:
            raise ValueError('spec/lines: Not ready for type {:s}'.format(ltype))

        # Init
        if not isinstance(trans,(Quantity,basestring)):
            raise ValueError('Rest wavelength must be a Quantity or str')

        # Other
        self.data = {} # Atomic/Moleculare Data (e.g. f-value, A coefficient, Elow)
        self.analy = {'spec': None, # Analysis inputs (e.g. spectrum; from .clm file or AbsID)
            'wvlim': [0., 0.], # Wavelength interval about the line (observed)
            'vlim': [0., 0.]*u.km/u.s, # Velocity limit of line, relative to self.attrib['z']
            'do_analysis': 1 # Analyze
            }
        self.attrib = {   # Properties (e.g. column, EW, centroid)
                       'RA': 0.*u.deg, 'Dec': 0.*u.deg,  #  Coords
                       'z': 0., 'zsig': 0.,  #  Redshift
                       'v': 0.*u.km/u.s, 'vsig': 0.*u.km/u.s,  #  Velocity relative to z
                       'EW': 0.*u.AA, 'EWsig': 0.*u.AA, 'flgEW': 0 # EW
                       }

        # Fill data
        self.fill_data(trans, linelist=linelist)

    # Setup spectrum for analysis
    def cut_spec(self, normalize=False):
        '''Splice spectrum.  Normalize too (as desired)

        Parameters:
        ----------
        normalize: bool, optional
          Normalize if true (and continuum exists)

        Returns:
        ----------
        fx, sig, wave -- Arrays (numpy or Quantity) of flux, error, wavelength
        '''
        # Checks
        if np.sum(self.analy['wvlim']) == 0.:
            raise ValueError('spectralline.cut_spec: Need to set wvlim!') # Could use VMNX
        if self.analy['spec'] is None:
            raise ValueError('spectralline.cut_spec: Need to set spectrum!')
        if self.analy['spec'].wcs.unit == 1.:
            raise ValueError('Expecting a unit!')

        # Pixels for evaluation
        pix = self.analy['spec'].pix_minmax(self.analy['wvlim'])[0]

        # Cut for analysis
        fx = self.analy['spec'].flux[pix]
        sig = self.analy['spec'].sig[pix]
        wave = self.analy['spec'].dispersion[pix]

        # Normalize
        if normalize:
            try:
                fx = fx / self.analy['spec'].conti[pix]
            except AttributeError:
                pass
            else:
                sig = sig / self.analy['spec'].conti[pix]

        # Return
        return fx, sig, wave


    # EW 
    def box_ew(self):
        """  EW calculation
        Default is simple boxcar integration
        Observer frame, not rest-frame
          wvlim must be set!
          spec must be set!

        Parameters
        ----------

        Returns:
          EW, sigEW : EW and error in observer frame
        """
        # Cut spectrum
        fx, sig, wv = self.cut_spec(normalize=True)

        # dwv
        dwv = wv - np.roll(wv,1)
        dwv[0] = dwv[1]


        # Simple boxcar
        EW = np.sum( dwv * (1. - fx) ) 
        varEW = np.sum( dwv**2 * sig**2 )
        sigEW = np.sqrt(varEW) 


        # Fill
        self.attrib['EW'] = EW 
        self.attrib['sigEW'] = sigEW 

        # Return
        return EW, sigEW
            
    # EW 
    def restew(self):
        """  Rest EW calculation
        Return rest-frame.  See "box_ew" above for details
        """
        # Standard call
        EW,sigEW = self.box_ew()
        # Push to rest-frame
        self.attrib['EW'] = EW / (self.attrib['z']+1)
        self.attrib['sigEW'] = sigEW / (self.attrib['z']+1)

        # Return
        return self.attrib['EW'], self.attrib['sigEW'] 

    # Output
    def __repr__(self):
        txt = '[{:s}:'.format(self.__class__.__name__)
        try:
            txt = txt+' {:s},'.format(self.data['name'])
        except KeyError:
            pass
        txt = txt + ' wrest={:g}'.format(self.wrest)
        txt = txt + ']'
        return (txt)

# Class for Generic Absorption Line System
class AbsLine(SpectralLine):
    """Spectral absorption line
    trans: Quantity or str
      Quantity: Rest wavelength (e.g. 1215.6700*u.AA)
      str: Name of transition (e.g. 'CIV 1548')
    """
    # Initialize with a .dat file
    def __init__(self, trans, linelist=None): 
        # Generate with type
        SpectralLine.__init__(self,'Abs', trans, linelist=linelist)

    def print_specline_type(self):
        """"Return a string representing the type of vehicle this is."""
        return 'AbsLine'

    def fill_data(self,trans, linelist=None):
        ''' Fill atomic data and setup analy
        Parameters:
        -----------
        trans: Quantity or str
          Quantity: Rest wavelength (e.g. 1215.6700*u.AA)
          str: Name of transition (e.g. 'CIV 1548')
        linelist : LineList, optional
          Class of linelist or str setting LineList
        '''

        # Deal with LineList
        if linelist is None:
            self.llist = LineList('ISM')
        elif isinstance(linelist,basestring):
            self.llist = LineList(linelist)
        elif isinstance(linelist,LineList):
            self.llist = linelist
        else:
            raise ValueError('Bad input for linelist')

        # Data
        self.data.update(self.llist[trans])

        # Update
        self.wrest = self.data['wrest']
        self.trans = self.data['name']

        #
        self.analy.update( {
            'flg_eye': 0,
            'flg_limit': 0, # No limit
            'datafile': '', 
            'name': self.data['name']
            })

        # Additional attributes for Absorption Line
        self.attrib.update({'N': 0., 'Nsig': 0., 'flagN': 0, # Column
                       'b': 0., 'bsig': 0.  # Doppler
                       } )

    # Perform AODM on the line
    def aodm(self, **kwargs): 
        """  AODM calculation

        Parameters
        ----------
        spec : Spectrum1D (None)
          1D spectrum.  Required but often read in through the Class (self.spec)
        conti : np.array (None)
          Continuum array 

        Returns:
          N, sigN : Column and error in linear space
        """

        # Grab Spectrum
        spec = self.set_spec(**kwargs)

        # Velocity array
        spec.velo = spec.relative_vel(self.wrest*(1+self.analy['z']))

        # Pixels for evaluation
        pix = spec.pix_minmax(self.analy['z'], self.wrest,
                        self.analy['vlim'].to('km/s'))[0]
                        #self.analy['vlim'].to('km/s').value)[0]

        # For convenience + normalize
        velo = spec.velo[pix]
        fx, sig = parse_spec(spec, **kwargs)

        # dv
        delv = velo - np.roll(velo,1)
        delv[0] = delv[1]

        # Atomic data
        assert False #  DEFINE 14.5761 or GENERATE
        cst = (10.**14.5761)/(self.data['fval']*self.wrest) / (u.km/u.s) / u.cm * (u.AA/u.cm)

        # Mask
        mask = (pix == pix) # True = good
        nndt = Quantity(np.zeros(len(pix)), unit='s/(km cm cm)')

        # Saturated?
        satp = np.where( (fx <= sig/5.) | (fx < 0.05) )[0]
        if len(satp) > 0:
            mask[satp] = False
            lim = np.where(sig[satp] > 0.)[0]
            if len(lim) > 0:
                sub = np.maximum(0.05, sig[satp[lim]]/5.)
                nndt[satp[lim]] = np.log(1./sub)*cst
                flg_sat = len(lim) 
                raise ValueError('USE FLG_SAT')
        # AODM
        nndt[mask] = np.log(1./fx[mask])*cst

        # Sum it
        ntot = np.sum( nndt*delv )
        tvar = np.sum( (delv*cst*sig/fx)**2 )

        # Fill
        self.attrib['N'] = ntot
        self.attrib['sigN'] = np.sqrt(tvar)
        logN, sig_logN = xsb.lin_to_log(self.attrib['N'].value, self.attrib['sigN'].value)
        self.attrib['logN'] = logN
        self.attrib['sig_logN'] = sig_logN

        # Return
        return ntot, np.sqrt(tvar)




    # Output
    def __repr__(self):
        txt = '[{:s}:'.format(self.__class__.__name__)
        # Name
        try:
            txt = txt+' {:s},'.format(self.data['name'])
        except KeyError:
            pass
        # wrest
        txt = txt + ' wrest={:.4f}'.format(self.wrest)
        # fval
        try:
            txt = txt+', f={:g}'.format(self.data['fval'])
        except KeyError:
            pass
        txt = txt + ']'
        return (txt)


## #################################    
## #################################    
## TESTING
## #################################    
if __name__ == '__main__':

    flg_test = 0
    #flg_test += 2**0  # AbsLine
    flg_test += 2**1  # AODM
    #flg_test += 2**2  # EW

    # Test AODM
    if (flg_test % 2**2) >= 2**1:
        print('------------ AODM -------------')
        # Spectrum
        fil = '~/PROGETTI/LLSZ3/data/normalize/UM669_nF.fits'
        aline = AbsLine(1302.1685*u.AA)
        aline.spec = lsio.readspec(fil)
        # Line info
        aline.analy['z'] = 2.92652
        aline.analy['vlim'] = const.c.to('km/s') * (
                    ( np.array([5110.668, 5116.305])*u.AA/(
                        1+aline.analy['z']) - aline.wrest) / aline.wrest )
        # Evaluate
        N,sigN = aline.aodm(conti=np.ones(len(aline.spec.flux)))
        logN, sig_logN = xsb.lin_to_log(N,sigN)
        print('logN = {:g}, sig_logN = {:g}'.format(logN, sig_logN))
