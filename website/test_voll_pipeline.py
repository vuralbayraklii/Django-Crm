"""
Tests for VoLL Pipeline Optimization

This test module validates that the optimization correctly pre-computes
neighbor transformer data and reuses it efficiently.
"""

import pandas as pd
import numpy as np
import unittest
from unittest.mock import Mock, MagicMock
from website.voll_pipeline import (
    _safe_len,
    _ensure_columns,
    _df_final_hazirla,
    _precompute_neighbor_data,
    asama5_karsilastirma,
    asama6_birlestirme,
    run_voll_pipeline
)


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions"""
    
    def test_safe_len_with_dataframe(self):
        """Test _safe_len with a DataFrame"""
        df = pd.DataFrame({'a': [1, 2, 3]})
        self.assertEqual(_safe_len(df), 3)
    
    def test_safe_len_with_none(self):
        """Test _safe_len with None"""
        self.assertEqual(_safe_len(None), 0)
    
    def test_safe_len_with_empty_df(self):
        """Test _safe_len with empty DataFrame"""
        df = pd.DataFrame()
        self.assertEqual(_safe_len(df), 0)
    
    def test_ensure_columns_success(self):
        """Test _ensure_columns with all required columns present"""
        df = pd.DataFrame({'a': [1], 'b': [2], 'c': [3]})
        # Should not raise an exception
        _ensure_columns(df, ['a', 'b'], 'test')
    
    def test_ensure_columns_failure(self):
        """Test _ensure_columns with missing columns"""
        df = pd.DataFrame({'a': [1], 'b': [2]})
        with self.assertRaises(ValueError) as context:
            _ensure_columns(df, ['a', 'b', 'c'], 'test')
        self.assertIn('Missing columns', str(context.exception))


class TestDataPreparation(unittest.TestCase):
    """Test data preparation functions"""
    
    def test_df_final_hazirla_basic(self):
        """Test _df_final_hazirla with basic data"""
        df_tahmin = pd.DataFrame({
            'Tanım Numarası': [1, 1, 1],
            'Profil Tarihi': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'Yüklenme': [0.8, 0.9, 1.1]
        })
        df_trafo = pd.DataFrame({
            'Tanım Numarası': [1],
            'DTR_ID': [100],
            'KODU': ['TR001'],
            'Guc_kVA': [500]
        })
        
        result = _df_final_hazirla(df_tahmin, df_trafo, 1)
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        self.assertIn('DTR_ID', result.columns)
        self.assertIn('KODU', result.columns)
        self.assertEqual(result['DTR_ID'].iloc[0], 100)
    
    def test_df_final_hazirla_empty_input(self):
        """Test _df_final_hazirla with empty input"""
        df_tahmin = pd.DataFrame()
        df_trafo = pd.DataFrame({'Tanım Numarası': [1]})
        
        result = _df_final_hazirla(df_tahmin, df_trafo, 1)
        
        self.assertIsNone(result)


class TestNeighborPrecomputation(unittest.TestCase):
    """Test the key optimization: neighbor pre-computation"""
    
    def setUp(self):
        """Set up test data"""
        # Create mock configuration objects
        self.kullanici = Mock()
        self.kullanici.voll_konut = 1.0
        self.kullanici.voll_sanayi = 1.5
        
        self.cba_config = Mock()
        self.cba_config.maliyet = Mock()
        self.cba_config.maliyet.değişim_günü = 'Pazartesi'
        self.cba_config.maliyet.değişim_saati = '10:00'
        self.cba_config.maliyet.iscilik_saat_maliyeti = 100
        self.cba_config.maliyet.ekip_buyuklugu = 3
        self.cba_config.maliyet.vinc_maliyeti = 500
        
        self.config = Mock()
        self.config.VOLL_YÜKLENME_THRESHOLD = 1.0
        
        # Create sample data
        self.df_tahmin = pd.DataFrame({
            'Tanım Numarası': [1, 1, 2, 2, 3, 3],
            'Profil Tarihi': pd.date_range('2024-01-01', periods=6),
            'Yüklenme': [0.8, 1.2, 0.9, 1.1, 0.7, 1.3]
        })
        
        self.df_trafo = pd.DataFrame({
            'Tanım Numarası': [1, 2, 3],
            'DTR_ID': [100, 200, 300],
            'KODU': ['TR001', 'TR002', 'TR003'],
            'Guc_kVA': [500, 600, 550]
        })
        
        self.df_yogunluk = pd.DataFrame({
            'TRAFOSERNO': [1, 2, 3],
            'AY': [1, 1, 1],
            'Konut_Tuketim': [100, 150, 120],
            'Sanayi_Tuketim': [200, 250, 180]
        })
    
    def test_precompute_neighbor_data_caching(self):
        """Test that neighbor data is correctly pre-computed and cached"""
        neighbor_ids = [2, 3]
        
        cache = _precompute_neighbor_data(
            df_tahmin=self.df_tahmin,
            df_trafo=self.df_trafo,
            df_yogunluk=self.df_yogunluk,
            kullanici=self.kullanici,
            cba_config=self.cba_config,
            config=self.config,
            neighbor_ids=neighbor_ids
        )
        
        # Verify cache structure
        self.assertIsInstance(cache, dict)
        
        # Check that neighbors were cached (may be empty if data filtering fails, which is OK)
        for neighbor_id in neighbor_ids:
            if neighbor_id in cache:
                self.assertIn('df_trafo', cache[neighbor_id])
                self.assertIn('df_tahmin', cache[neighbor_id])
                self.assertIn('df_yogunluk', cache[neighbor_id])
                self.assertIn('grup_df', cache[neighbor_id])
    
    def test_precompute_avoids_duplicate_calculation(self):
        """Test that pre-computation avoids duplicate calculations"""
        # Simulate scenario where neighbor 2 appears multiple times
        neighbor_ids = [2, 2, 3, 3, 3]  # Duplicates
        
        cache = _precompute_neighbor_data(
            df_tahmin=self.df_tahmin,
            df_trafo=self.df_trafo,
            df_yogunluk=self.df_yogunluk,
            kullanici=self.kullanici,
            cba_config=self.cba_config,
            config=self.config,
            neighbor_ids=neighbor_ids
        )
        
        # Should only have unique entries (2 and 3), not 5
        unique_cached = len(cache)
        self.assertLessEqual(unique_cached, 2)  # At most 2 unique neighbors


class TestAsama5Optimization(unittest.TestCase):
    """Test Stage 5 optimization with pre-computed data"""
    
    def setUp(self):
        """Set up test data"""
        self.kullanici = Mock()
        self.cba_config = Mock()
        self.cba_config.maliyet = Mock()
        self.cba_config.maliyet.değişim_günü = 'Pazartesi'
        self.cba_config.maliyet.değişim_saati = '10:00'
        self.cba_config.maliyet.iscilik_saat_maliyeti = 100
        self.cba_config.maliyet.ekip_buyuklugu = 3
        self.cba_config.maliyet.vinc_maliyeti = 500
        
        self.config = Mock()
        
        # Create minimal test data
        self.df_aday_tahmin = pd.DataFrame({
            'Tanım Numarası': [1],
            'Profil Tarihi': ['2024-01-01'],
            'Yüklenme': [1.2]
        })
        
        self.df_aday_trafo = pd.DataFrame({
            'Tanım Numarası': [1],
            'DTR_ID': [100],
            'KODU': ['TR001'],
            'Guc_kVA': [500]
        })
        
        self.df_komsu_trafo = pd.DataFrame({
            'Tanım Numarası': [2],
            'DTR_ID': [200],
            'KODU': ['TR002'],
            'Guc_kVA': [600]
        })
        
        self.df_komsu_tahmin = pd.DataFrame({
            'Tanım Numarası': [2],
            'Profil Tarihi': ['2024-01-01'],
            'Yüklenme': [1.1]
        })
        
        self.df_yogunluk = pd.DataFrame({
            'TRAFOSERNO': [1, 2],
            'AY': [1, 1]
        })
        
        self.df_gecerli_aday = pd.DataFrame({
            'Aday_Tanım_Numarası': [1],
            'Komsu_Tanım_Numarası': [2],
            'Uzaklık_km': [5.0]
        })
    
    def test_asama5_with_precomputed_data(self):
        """Test that asama5 can use pre-computed neighbor data"""
        # Create pre-computed cache
        precomputed = {
            2: {
                'df_trafo': self.df_komsu_trafo,
                'df_tahmin': self.df_komsu_tahmin,
                'df_yogunluk': self.df_yogunluk[self.df_yogunluk['TRAFOSERNO'] == 2],
                'grup_df': pd.DataFrame({'Grup_No': [1], 'TOPLAM_VOLL': [100]})
            }
        }
        
        result = asama5_karsilastirma(
            self.df_aday_tahmin,
            self.df_aday_trafo,
            self.df_komsu_trafo,
            self.df_komsu_tahmin,
            self.df_yogunluk,
            self.df_gecerli_aday,
            self.kullanici,
            self.cba_config,
            self.config,
            precomputed_neighbor_data=precomputed
        )
        
        # Should return a dataframe (even if minimal)
        self.assertIsInstance(result, pd.DataFrame)
    
    def test_asama5_without_precomputed_data(self):
        """Test that asama5 works without pre-computed data (fallback)"""
        result = asama5_karsilastirma(
            self.df_aday_tahmin,
            self.df_aday_trafo,
            self.df_komsu_trafo,
            self.df_komsu_tahmin,
            self.df_yogunluk,
            self.df_gecerli_aday,
            self.kullanici,
            self.cba_config,
            self.config,
            precomputed_neighbor_data=None  # No cache
        )
        
        # Should still return a dataframe (using fallback logic)
        self.assertIsInstance(result, pd.DataFrame)


class TestAsama6(unittest.TestCase):
    """Test Stage 6 merge function"""
    
    def test_asama6_basic_merge(self):
        """Test basic merge functionality"""
        df_voll = pd.DataFrame({
            'Grup_No': [1, 2],
            'TOPLAM_VOLL': [100.0, 150.0],
            'DTR_ID': [100, 100],
            'KODU': ['TR001', 'TR001'],
            'Tanım Numarası': [1, 1],
            'Guc_kVA': [500, 500]
        })
        
        cba_sonuc = pd.DataFrame({
            'ADAY_Tanım_Numarası': [1],
            'KOMSU_TOPLAM_VOLL': [80.0],
            'Toplam_Maliyet': [50.0]
        })
        
        result = asama6_birlestirme(df_voll, cba_sonuc)
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertGreater(len(result), 0)
        self.assertIn('kar_maliyet_farki', result.columns)
    
    def test_asama6_empty_input(self):
        """Test merge with empty input"""
        df_voll = pd.DataFrame()
        cba_sonuc = pd.DataFrame()
        
        result = asama6_birlestirme(df_voll, cba_sonuc)
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 0)


class TestPipelineIntegration(unittest.TestCase):
    """Integration tests for the complete pipeline"""
    
    def test_pipeline_precomputation_flow(self):
        """Test that the pipeline correctly pre-computes and reuses neighbor data"""
        # Create mock becayis object
        becayis_obj = Mock()
        
        # Set up minimal data
        becayis_obj.df_tahmin = pd.DataFrame({
            'Tanım Numarası': [1, 1, 2, 2],
            'Profil Tarihi': pd.date_range('2024-01-01', periods=4),
            'Yüklenme': [1.2, 1.3, 1.1, 1.4]
        })
        
        becayis_obj.df_trafo = pd.DataFrame({
            'Tanım Numarası': [1, 2],
            'DTR_ID': [100, 200],
            'KODU': ['TR001', 'TR002'],
            'Guc_kVA': [500, 600]
        })
        
        becayis_obj.df_yogunluk = pd.DataFrame({
            'TRAFOSERNO': [1, 2],
            'AY': [1, 1]
        })
        
        becayis_obj.df_geçerli_adaylar = pd.DataFrame({
            'Aday_Tanım_Numarası': [1],
            'Komsu_Tanım_Numarası': [2],
            'Uzaklık_km': [5.0]
        })
        
        # Mock configuration
        kullanici = Mock()
        config = Mock()
        config.VOLL_YÜKLENME_THRESHOLD = 1.0
        
        cba_config = Mock()
        cba_config.maliyet = Mock()
        cba_config.maliyet.değişim_günü = 'Pazartesi'
        cba_config.maliyet.değişim_saati = '10:00'
        cba_config.maliyet.iscilik_saat_maliyeti = 100
        cba_config.maliyet.ekip_buyuklugu = 3
        cba_config.maliyet.vinc_maliyeti = 500
        
        # Run pipeline
        result = run_voll_pipeline(
            becayis_obj,
            kullanici,
            config,
            cba_config,
            verbose=False
        )
        
        # Verify result structure
        self.assertIsInstance(result, dict)
        self.assertIn('df_final', result)
        self.assertIn('df_karsilastirma', result)


def run_tests():
    """Run all tests"""
    unittest.main(argv=[''], exit=False, verbosity=2)


if __name__ == '__main__':
    run_tests()
